"""Server-level integration for SDN CONTROLLERS + DNS + IPAMs (Wave 7c, full-surface
campaign).

Proves the trust gate holds across the new wiring:
- every read is an audited call at the exact path, recorded to the ledger;
- every mutation is dry-run by default (confirm=False => status="plan", op NOT called);
- a confirm=True call routes to the real op and records to the ledger;
- risk ladder through the SERVER wrapper (not just the bare plan factory): create/update are
  LOW, delete is MEDIUM, across all three families;
- PENDING/apply-gated framing (no "LIVE/IMMEDIATE" language — this family is NOT the vnet
  firewall's live-effect model) present on every mutation plan;
- THE REINSTATED SECRET RULING end-to-end through the wrapper (Wave 7c review HIGH-1):
  dns_get/ipam_get STRIP their secret-shaped field (`key`/`token`) entirely at the read
  layer, mirroring pbs_metrics.py's influxdb_http_get mechanism — while
  dns_update/dns_delete/ipam_update/ipam_delete's PLAN never carries the raw secret and the
  raw ledger BYTES never carry it either;
- THE URL-USERINFO RULING (HIGH-2): an embedded HTTP Basic-auth credential in `url` is
  masked (host visible, userinfo stripped) at the same read layer and in plan/ledger text.

Backend is faked; the ledger is real (tmp_path) so PLAN->PROVE is exercised end to end.
Mirrors the `_wire()`/`_FakeApi` idiom in tests/test_server_sdn_firewall_wiring.py.
"""

from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest

import proximo.server as server
from proximo import taint
from proximo.audit import AuditLedger
from proximo.config import ProximoConfig

FINGERPRINT = ":".join(["ab"] * 32)


class _FakeApi:
    def __init__(self):
        self.config = SimpleNamespace(node="pve")
        self.gets: list = []
        self.posts: list = []
        self.puts: list = []
        self.dels: list = []
        self._get_return: object = []

    def _get(self, path):
        self.gets.append(path)
        return self._get_return

    def _post(self, path, data=None):
        self.posts.append((path, data))
        return None

    def _put(self, path, data=None):
        self.puts.append((path, data))
        return None

    def _delete(self, path, params=None):
        self.dels.append((path, params))
        return None


def _wire(tmp_path, monkeypatch):
    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(api_base_url="https://x:8006/api2/json", node="pve",
                        token_path="/run/x", audit_log_path=log)
    api = _FakeApi()
    ledger = AuditLedger(log)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, api, SimpleNamespace(), ledger))
    return cfg, api, ledger, log


def _entries(log: str) -> list[dict]:
    with open(log, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _confirmed_entry(log: str, action: str) -> dict:
    entries = [e for e in _entries(log) if e["action"] == action and e["outcome"] == "ok"]
    assert len(entries) == 1, f"expected exactly one confirmed {action!r} entry, got {entries}"
    return entries[0]


# --- controllers — reads --------------------------------------------------------------------


def test_controllers_list_is_audited_read(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = [{"controller": "ctrl1", "type": "bgp"}]
    out = server.pve_sdn_controllers_list()
    assert api.gets == ["/cluster/sdn/controllers"]
    assert out == [{"controller": "ctrl1", "type": "bgp"}]
    assert any(e.get("action") == "pve_sdn_controllers_list" for e in _entries(log))


def test_controller_get_is_audited_read(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = {"controller": "ctrl1", "type": "bgp"}
    out = server.pve_sdn_controller_get("ctrl1")
    assert api.gets == ["/cluster/sdn/controllers/ctrl1"]
    assert out == {"controller": "ctrl1", "type": "bgp"}
    assert any(e.get("action") == "pve_sdn_controller_get" for e in _entries(log))


# --- controllers — mutations ----------------------------------------------------------------


def test_controller_create_dry_run_low_then_confirm(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    dry = server.pve_sdn_controller_create("ctrl1", "bgp", options={"asn": 65000})
    assert dry["status"] == "plan" and dry["risk"] == "low"
    assert api.posts == []
    server.pve_sdn_controller_create("ctrl1", "bgp", options={"asn": 65000}, confirm=True)
    assert api.posts == [("/cluster/sdn/controllers", {"type": "bgp", "controller": "ctrl1", "asn": 65000})]
    entry = _confirmed_entry(log, "pve_sdn_controller_create")
    assert entry["mutation"] is True


def test_controller_update_dry_run_low_then_confirm(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    dry = server.pve_sdn_controller_update("ctrl1", options={"asn": 65001})
    assert dry["status"] == "plan" and dry["risk"] == "low"
    assert api.puts == []
    server.pve_sdn_controller_update("ctrl1", options={"asn": 65001}, confirm=True)
    assert api.puts == [("/cluster/sdn/controllers/ctrl1", {"asn": 65001})]


def test_controller_delete_dry_run_medium_then_confirm(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = [{"controller": "ctrl1", "type": "bgp"}]
    dry = server.pve_sdn_controller_delete("ctrl1")
    assert dry["status"] == "plan" and dry["risk"] == "medium"
    assert api.dels == []
    server.pve_sdn_controller_delete("ctrl1", confirm=True)
    assert api.dels == [("/cluster/sdn/controllers/ctrl1", {})]
    assert any(e.get("action") == "pve_sdn_controller_delete" for e in _entries(log))


def test_controller_mutations_never_softened_by_live_language(tmp_path, monkeypatch):
    """This family is PENDING/apply-gated, NOT the vnet firewall's LIVE/IMMEDIATE model —
    every mutation plan states the apply gate, never claims an immediate live effect."""
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    dry = server.pve_sdn_controller_create("ctrl1", "bgp")
    blast = " ".join(dry["blast_radius"]).lower()
    assert "inert until pve_sdn_apply" in blast
    assert "live/immediate" not in blast


# --- dns — reads (secret-ruling headline) ---------------------------------------------------


def test_dns_list_is_audited_read(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = [{"dns": "dns1", "type": "powerdns"}]
    out = server.pve_sdn_dns_list()
    assert api.gets == ["/cluster/sdn/dns"]
    assert out == [{"dns": "dns1", "type": "powerdns"}]
    assert any(e.get("action") == "pve_sdn_dns_list" for e in _entries(log))


def test_dns_get_strips_key_at_read_layer(tmp_path, monkeypatch):
    """THE REINSTATED RULING, proven at the server layer: dns_get STRIPS `key` at the read
    layer (removed entirely) — mirrors pbs_metrics.py's influxdb_http_get mechanism exactly.
    (Wave 7c review HIGH-1 — this test previously locked in the opposite, backwards
    behavior.)"""
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    api._get_return = {"dns": "dns1", "type": "powerdns", "key": "raw-key-from-api"}
    out = server.pve_sdn_dns_get("dns1")
    assert "key" not in out
    assert "raw-key-from-api" not in str(out)


def test_dns_get_non_secret_fields_survive_the_strip_untouched(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    api._get_return = {"dns": "dns1", "type": "powerdns", "ttl": 300, "key": "raw-key-from-api"}
    out = server.pve_sdn_dns_get("dns1")
    assert out == {"dns": "dns1", "type": "powerdns", "ttl": 300}


def test_dns_get_masks_url_userinfo_at_read_layer(tmp_path, monkeypatch):
    """HIGH-2, proven at the server layer: an embedded HTTP Basic-auth credential in `url`
    is masked (host visible, userinfo stripped) on the bare read tool's own return."""
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    api._get_return = {"dns": "dns1", "url": "http://admin:hunter2@pdns.example.com:8080"}
    out = server.pve_sdn_dns_get("dns1")
    assert "hunter2" not in out["url"]
    assert "pdns.example.com:8080" in out["url"]


# --- dns — mutations (secret-ruling headline) -----------------------------------------------


_DNS_KEY_SENTINEL = "sentinel-dns-key-value"  # noqa: S105 (test sentinel, not a real credential)


def test_dns_create_dry_run_low_then_confirm_key_forwarded_raw(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    dry = server.pve_sdn_dns_create("dns1", "https://pdns.example.com", _DNS_KEY_SENTINEL)
    assert dry["status"] == "plan" and dry["risk"] == "low"
    assert _DNS_KEY_SENTINEL not in json.dumps(dry)
    assert api.posts == []

    server.pve_sdn_dns_create("dns1", "https://pdns.example.com", _DNS_KEY_SENTINEL, confirm=True)
    assert api.posts == [("/cluster/sdn/dns", {
        "type": "powerdns", "dns": "dns1", "url": "https://pdns.example.com", "key": _DNS_KEY_SENTINEL,
    })]

    entries = _entries(log)
    assert all(_DNS_KEY_SENTINEL not in json.dumps(e) for e in entries)
    entry = _confirmed_entry(log, "pve_sdn_dns_create")
    assert "key" not in entry["detail"]

    raw = open(log, "rb").read()
    assert _DNS_KEY_SENTINEL.encode("utf-8") not in raw
    assert b"https://pdns.example.com" in raw  # url is NOT secret — visible raw


def test_dns_update_dry_run_captures_and_redacts_current(tmp_path, monkeypatch):
    """`key` is stripped entirely at the read layer (dns_get, HIGH-1) — absent from
    dry["current"], not present as "[redacted]"."""
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = {"dns": "dns1", "type": "powerdns", "key": "leaked-from-get", "ttl": 100}
    dry = server.pve_sdn_dns_update("dns1", dns_ttl=300)
    assert dry["status"] == "plan"
    assert "key" not in dry["current"]
    assert "leaked-from-get" not in json.dumps(dry)

    server.pve_sdn_dns_update("dns1", dns_ttl=300, confirm=True)
    assert api.puts == [("/cluster/sdn/dns/dns1", {"ttl": 300})]

    raw = open(log, "rb").read()
    assert b"leaked-from-get" not in raw


def test_dns_update_new_key_never_writes_to_ledger(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = {"dns": "dns1"}
    server.pve_sdn_dns_update("dns1", key=_DNS_KEY_SENTINEL, confirm=True)
    assert api.puts == [("/cluster/sdn/dns/dns1", {"key": _DNS_KEY_SENTINEL})]
    raw = open(log, "rb").read()
    assert _DNS_KEY_SENTINEL.encode("utf-8") not in raw


def test_dns_delete_dry_run_medium_captures_redacted_then_confirm(tmp_path, monkeypatch):
    """`key` is stripped entirely at the read layer — absent from dry["current"]."""
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = {"dns": "dns1", "key": "leaked-from-get"}
    dry = server.pve_sdn_dns_delete("dns1")
    assert dry["status"] == "plan" and dry["risk"] == "medium"
    assert "key" not in dry["current"]
    assert api.dels == []

    server.pve_sdn_dns_delete("dns1", confirm=True)
    assert api.dels == [("/cluster/sdn/dns/dns1", {})]

    raw = open(log, "rb").read()
    assert b"leaked-from-get" not in raw


# --- ipams — reads (secret-ruling headline, mirror of dns) ------------------------------------


def test_ipams_list_is_audited_read(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = [{"ipam": "ipam1", "type": "netbox"}]
    out = server.pve_sdn_ipams_list()
    assert api.gets == ["/cluster/sdn/ipams"]
    assert out == [{"ipam": "ipam1", "type": "netbox"}]
    assert any(e.get("action") == "pve_sdn_ipams_list" for e in _entries(log))


def test_ipam_get_strips_token_at_read_layer(tmp_path, monkeypatch):
    """THE REINSTATED RULING, mirror of dns_get, proven at the server layer. (Wave 7c review
    HIGH-1 — this test previously locked in the opposite, backwards behavior.)"""
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    api._get_return = {"ipam": "ipam1", "type": "netbox", "token": "raw-token-from-api"}
    out = server.pve_sdn_ipam_get("ipam1")
    assert "token" not in out
    assert "raw-token-from-api" not in str(out)


def test_ipam_get_non_secret_fields_survive_the_strip_untouched(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    api._get_return = {"ipam": "ipam1", "type": "netbox", "section": 3, "token": "raw-token-from-api"}
    out = server.pve_sdn_ipam_get("ipam1")
    assert out == {"ipam": "ipam1", "type": "netbox", "section": 3}


def test_ipam_get_masks_url_userinfo_at_read_layer(tmp_path, monkeypatch):
    """HIGH-2, proven at the server layer, mirror of dns_get."""
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    api._get_return = {"ipam": "ipam1", "url": "http://admin:hunter2@netbox.example.com:8080"}
    out = server.pve_sdn_ipam_get("ipam1")
    assert "hunter2" not in out["url"]
    assert "netbox.example.com:8080" in out["url"]


def test_ipam_status_is_audited_read_and_adversarial_classified(tmp_path, monkeypatch):
    """ipam_status is the sole ADVERSARIAL tool in this module — verify the taint marker is
    set when tracking is enabled (proves the classification is actually WIRED, not just
    listed in ADVERSARIAL_TOOLS)."""
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = [{"ip": "192.0.2.50", "mac": "aa:bb:cc:dd:ee:ff", "hostname": "guest1"}]
    monkeypatch.setenv("PROXIMO_TAINT_TRACK", "1")
    out = server.pve_sdn_ipam_status("ipam1")
    assert api.gets == ["/cluster/sdn/ipams/ipam1/status"]
    assert out == [{"ip": "192.0.2.50", "mac": "aa:bb:cc:dd:ee:ff", "hostname": "guest1"}]
    assert taint.is_adversarial("pve_sdn_ipam_status")
    assert taint.is_tainted(os.path.dirname(log))


# --- ipams — mutations (secret-ruling headline, mirror of dns) --------------------------------


_IPAM_TOKEN_SENTINEL = "sentinel-ipam-token-value"  # noqa: S105 (test sentinel, not a real credential)


def test_ipam_create_dry_run_low_then_confirm_token_forwarded_raw(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    dry = server.pve_sdn_ipam_create("ipam1", "netbox", url="https://netbox.example.com",
                                     token=_IPAM_TOKEN_SENTINEL)
    assert dry["status"] == "plan" and dry["risk"] == "low"
    assert _IPAM_TOKEN_SENTINEL not in json.dumps(dry)
    assert api.posts == []

    server.pve_sdn_ipam_create("ipam1", "netbox", url="https://netbox.example.com",
                                token=_IPAM_TOKEN_SENTINEL, confirm=True)
    assert api.posts == [("/cluster/sdn/ipams", {
        "type": "netbox", "ipam": "ipam1", "url": "https://netbox.example.com",
        "token": _IPAM_TOKEN_SENTINEL,
    })]

    entries = _entries(log)
    assert all(_IPAM_TOKEN_SENTINEL not in json.dumps(e) for e in entries)
    entry = _confirmed_entry(log, "pve_sdn_ipam_create")
    assert "token" not in entry["detail"]

    raw = open(log, "rb").read()
    assert _IPAM_TOKEN_SENTINEL.encode("utf-8") not in raw
    assert b"https://netbox.example.com" in raw  # url is NOT secret — visible raw


def test_ipam_update_dry_run_captures_and_redacts_current(tmp_path, monkeypatch):
    """`token` is stripped entirely at the read layer (ipam_get, HIGH-1) — absent from
    dry["current"], not present as "[redacted]"."""
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = {"ipam": "ipam1", "type": "netbox", "token": "leaked-from-get", "section": 1}
    dry = server.pve_sdn_ipam_update("ipam1", section=5)
    assert dry["status"] == "plan"
    assert "token" not in dry["current"]
    assert "leaked-from-get" not in json.dumps(dry)

    server.pve_sdn_ipam_update("ipam1", section=5, confirm=True)
    assert api.puts == [("/cluster/sdn/ipams/ipam1", {"section": 5})]

    raw = open(log, "rb").read()
    assert b"leaked-from-get" not in raw


def test_ipam_update_new_token_never_writes_to_ledger(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = {"ipam": "ipam1"}
    server.pve_sdn_ipam_update("ipam1", token=_IPAM_TOKEN_SENTINEL, confirm=True)
    assert api.puts == [("/cluster/sdn/ipams/ipam1", {"token": _IPAM_TOKEN_SENTINEL})]
    raw = open(log, "rb").read()
    assert _IPAM_TOKEN_SENTINEL.encode("utf-8") not in raw


def test_ipam_delete_dry_run_medium_captures_redacted_then_confirm(tmp_path, monkeypatch):
    """`token` is stripped entirely at the read layer — absent from dry["current"]."""
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = {"ipam": "ipam1", "token": "leaked-from-get"}
    dry = server.pve_sdn_ipam_delete("ipam1")
    assert dry["status"] == "plan" and dry["risk"] == "medium"
    assert "token" not in dry["current"]
    assert api.dels == []

    server.pve_sdn_ipam_delete("ipam1", confirm=True)
    assert api.dels == [("/cluster/sdn/ipams/ipam1", {})]

    raw = open(log, "rb").read()
    assert b"leaked-from-get" not in raw


# --- HIGH-2: url userinfo credential, end-to-end raw-ledger-bytes proof ----------------------
#
# Unit-level shapes (embedded literal '@' in password, IPv6 host, no-userinfo passthrough) are
# covered directly against `_redact_url_userinfo` in tests/test_sdn_objects.py; these prove the
# SAME masking end-to-end through the server wrapper + a real ledger, with an allowlist-safe,
# low-entropy @-bearing sentinel (the userinfo portion is hyphenated/all-lowercase, and the host
# is an already-allowlisted `.example.com` — matches this repo's fixture-sentinel discipline).

_DNS_URL_USERINFO_SENTINEL = "http://sentinel-proxyuser:sentinel-proxypass@pdns.example.com:3128"
_IPAM_URL_USERINFO_SENTINEL = "http://sentinel-proxyuser:sentinel-proxypass@netbox.example.com:3128"


def test_dns_create_url_userinfo_masked_in_plan_but_forwarded_raw_end_to_end(tmp_path, monkeypatch):
    """An @-bearing url sentinel is forwarded RAW to the wire (the create must actually work)
    but the raw ledger BYTES never carry the userinfo credential portion — only the masked
    form and the visible host reach the ledger."""
    _, api, _, log = _wire(tmp_path, monkeypatch)
    dry = server.pve_sdn_dns_create("dns1", _DNS_URL_USERINFO_SENTINEL, _DNS_KEY_SENTINEL)
    assert "sentinel-proxypass" not in json.dumps(dry)
    assert "pdns.example.com" in json.dumps(dry)

    server.pve_sdn_dns_create("dns1", _DNS_URL_USERINFO_SENTINEL, _DNS_KEY_SENTINEL, confirm=True)
    assert api.posts == [("/cluster/sdn/dns", {
        "type": "powerdns", "dns": "dns1", "url": _DNS_URL_USERINFO_SENTINEL, "key": _DNS_KEY_SENTINEL,
    })]

    raw = open(log, "rb").read()
    assert b"sentinel-proxypass" not in raw
    assert b"pdns.example.com" in raw


def test_dns_update_url_userinfo_captured_and_masked_end_to_end(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = {"dns": "dns1", "url": _DNS_URL_USERINFO_SENTINEL, "key": "leaked-from-get"}
    dry = server.pve_sdn_dns_update("dns1", dns_ttl=300)
    assert "sentinel-proxypass" not in json.dumps(dry)
    assert "pdns.example.com" in dry["current"]["url"]

    server.pve_sdn_dns_update("dns1", dns_ttl=300, confirm=True)

    raw = open(log, "rb").read()
    assert b"sentinel-proxypass" not in raw
    assert b"pdns.example.com" in raw


def test_ipam_create_url_userinfo_masked_in_plan_but_forwarded_raw_end_to_end(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    dry = server.pve_sdn_ipam_create(
        "ipam1", "netbox", url=_IPAM_URL_USERINFO_SENTINEL, token=_IPAM_TOKEN_SENTINEL,
    )
    assert "sentinel-proxypass" not in json.dumps(dry)
    assert "netbox.example.com" in json.dumps(dry)

    server.pve_sdn_ipam_create(
        "ipam1", "netbox", url=_IPAM_URL_USERINFO_SENTINEL, token=_IPAM_TOKEN_SENTINEL, confirm=True,
    )
    assert api.posts == [("/cluster/sdn/ipams", {
        "type": "netbox", "ipam": "ipam1", "url": _IPAM_URL_USERINFO_SENTINEL,
        "token": _IPAM_TOKEN_SENTINEL,
    })]

    raw = open(log, "rb").read()
    assert b"sentinel-proxypass" not in raw
    assert b"netbox.example.com" in raw


def test_ipam_update_url_userinfo_captured_and_masked_end_to_end(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    api._get_return = {"ipam": "ipam1", "url": _IPAM_URL_USERINFO_SENTINEL, "token": "leaked-from-get"}
    dry = server.pve_sdn_ipam_update("ipam1", section=5)
    assert "sentinel-proxypass" not in json.dumps(dry)
    assert "netbox.example.com" in dry["current"]["url"]

    server.pve_sdn_ipam_update("ipam1", section=5, confirm=True)

    raw = open(log, "rb").read()
    assert b"sentinel-proxypass" not in raw
    assert b"netbox.example.com" in raw


# --- LOW-4: lock_token accepted by all 9 mutations (schema-verified) but never in the ledger -

_LOCK_TOKEN_SENTINEL = "sentinel-lock-token-value"  # noqa: S105 (test sentinel, not a real credential)

_LOCK_TOKEN_CASES = [
    pytest.param("pve_sdn_controller_create", dict(controller="ctrl1", controller_type="bgp"), id="controller_create"),
    pytest.param("pve_sdn_controller_update", dict(controller="ctrl1", options={"asn": 1}), id="controller_update"),
    pytest.param("pve_sdn_controller_delete", dict(controller="ctrl1"), id="controller_delete"),
    pytest.param("pve_sdn_dns_create", dict(dns="dns1", url="https://pdns.example.com", key="k1"), id="dns_create"),
    pytest.param("pve_sdn_dns_update", dict(dns="dns1", dns_ttl=300), id="dns_update"),
    pytest.param("pve_sdn_dns_delete", dict(dns="dns1"), id="dns_delete"),
    pytest.param("pve_sdn_ipam_create", dict(ipam="ipam1", ipam_type="netbox"), id="ipam_create"),
    pytest.param("pve_sdn_ipam_update", dict(ipam="ipam1", section=1), id="ipam_update"),
    pytest.param("pve_sdn_ipam_delete", dict(ipam="ipam1"), id="ipam_delete"),
]


@pytest.mark.parametrize("tool_name,kwargs", _LOCK_TOKEN_CASES)
def test_lock_token_forwarded_raw_never_writes_to_ledger(tmp_path, monkeypatch, tool_name, kwargs):
    """LOW-4: `lock_token` is accepted by all 9 mutations (schema-verified — every POST/PUT/
    DELETE on this plane carries a `lock-token` property) but `_audited()`'s `detail` is a
    fixed `{"confirmed": True}` literal that structurally cannot include it (matches the 7a
    `network.py` precedent) — there was no regression test locking this in for THIS module
    specifically (Wave 7c review LOW-4). Proves both directions: forwarded raw to the wire
    (the mutation must actually work) AND never in the raw ledger bytes."""
    _, api, _, log = _wire(tmp_path, monkeypatch)
    fn = getattr(server, tool_name)
    fn(confirm=True, lock_token=_LOCK_TOKEN_SENTINEL, **kwargs)

    forwarded = [d for _, d in (api.posts + api.puts) if d] + [p for _, p in api.dels if p]
    assert any(d.get("lock-token") == _LOCK_TOKEN_SENTINEL for d in forwarded), (
        f"{tool_name} confirm=True never forwarded lock_token to the wire"
    )

    raw = open(log, "rb").read()
    assert _LOCK_TOKEN_SENTINEL.encode("utf-8") not in raw
