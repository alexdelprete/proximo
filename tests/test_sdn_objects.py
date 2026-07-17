"""SDN CONTROLLERS + DNS + IPAMs tests (Wave 7c, full-surface campaign) — fully mocked, no
live Proxmox.

Mirrors test_sdn_firewall.py / test_network.py's own conventions:
- Op functions: a tiny fake api recording method/path/data (`_rec()`).
- Plan functions: fake apis giving just enough for each plan's own safe-read (CAPTURE) to
  resolve.
- Every test is self-contained — no shared mutable state.

Coverage:
 1. Validators — _check_controller_type/_check_dns_type/_check_ipam_type, _check_fingerprint,
    _check_no_control, _check_int, _check_controller_options (reserved-key guard),
    _redact_secrets (incl. url-userinfo masking), _redact_url_userinfo (the 5c/5d shapes —
    embedded literal '@', IPv6 host, no-userinfo passthrough), _strip_secrets_at_read
 2. Controllers — list/get URL construction, create/update/delete payload construction +
    `type` immutability on update, reserved-key smuggling guard
 3. DNS — list/get URL construction, create (required url/key) / update (reversev6mask
    ASENT, key/url optional) / delete payload construction; THE REINSTATED RULING — dns_get
    strips `key` at the read layer (Wave 7c review HIGH-1) and masks url userinfo (HIGH-2);
    secret redaction (again, defensively) in plan CAPTURE
 4. IPAMs — list/get/status URL construction, create/update (all optional)/delete payload
    construction; the mirror ruling for ipam_get (token stripped, url userinfo masked);
    secret redaction in plan CAPTURE, ipam_status raw passthrough (a separate,
    ADVERSARIAL-classified endpoint — unaffected by the secret ruling)
 5. Plan factories — risk ladder (LOW create/update, MEDIUM delete), CAPTURE-then-redact for
    update/delete previews (key/token now ABSENT from plan.current, not "[redacted]" — the
    read layer strips them first), url-userinfo masking in create/update plan text,
    "at least one field" guards, PENDING/apply-gated blast language, referential-integrity
    Smoke-confirm language
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from proximo.backends import ProximoError
from proximo.planning import RISK_LOW, RISK_MEDIUM
from proximo.sdn_objects import (
    _check_controller_options,
    _check_controller_type,
    _check_dns_type,
    _check_fingerprint,
    _check_int,
    _check_ipam_type,
    _check_no_control,
    _redact_secrets,
    _redact_url_userinfo,
    _strip_secrets_at_read,
    controller_create,
    controller_delete,
    controller_get,
    controller_update,
    controllers_list,
    dns_create,
    dns_delete,
    dns_get,
    dns_list,
    dns_update,
    ipam_create,
    ipam_delete,
    ipam_get,
    ipam_status,
    ipam_update,
    ipams_list,
    plan_controller_create,
    plan_controller_delete,
    plan_controller_update,
    plan_dns_create,
    plan_dns_delete,
    plan_dns_update,
    plan_ipam_create,
    plan_ipam_delete,
    plan_ipam_update,
)

FINGERPRINT = ":".join(["ab"] * 32)

# ---------------------------------------------------------------------------
# Fake api
# ---------------------------------------------------------------------------


def _rec():
    seen: dict = {}

    def g(path):
        seen["method"] = "GET"
        seen["path"] = path
        return seen.get("_get_return", [])

    def p(path, data=None):
        seen["method"] = "POST"
        seen["path"] = path
        seen["data"] = data
        return None

    def u(path, data=None):
        seen["method"] = "PUT"
        seen["path"] = path
        seen["data"] = data
        return None

    def d(path, params=None):
        seen["method"] = "DELETE"
        seen["path"] = path
        seen["params"] = params
        return None

    return SimpleNamespace(config=SimpleNamespace(node="pve"), _get=g, _post=p, _put=u, _delete=d, seen=seen)


def _boom_api():
    def _boom(_path):
        raise RuntimeError("api unavailable")
    return SimpleNamespace(config=SimpleNamespace(node="pve"), _get=_boom)


# ---------------------------------------------------------------------------
# 1. Validators
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["bgp", "evpn", "faucet", "isis"])
def test_check_controller_type_accepts_all_four(value):
    assert _check_controller_type(value) == value


def test_check_controller_type_rejects_unknown():
    with pytest.raises(ProximoError):
        _check_controller_type("openvpn")


def test_check_dns_type_accepts_powerdns():
    assert _check_dns_type("powerdns") == "powerdns"


def test_check_dns_type_rejects_unknown():
    with pytest.raises(ProximoError):
        _check_dns_type("bind9")


@pytest.mark.parametrize("value", ["netbox", "phpipam", "pve"])
def test_check_ipam_type_accepts_all_three(value):
    assert _check_ipam_type(value) == value


def test_check_ipam_type_rejects_unknown():
    with pytest.raises(ProximoError):
        _check_ipam_type("infoblox")


def test_check_fingerprint_accepts_valid():
    assert _check_fingerprint(FINGERPRINT) == FINGERPRINT


@pytest.mark.parametrize("value", ["AA:BB:CC:DD:EE:FF", "not-a-fingerprint", "ab" * 32])
def test_check_fingerprint_rejects_invalid(value):
    with pytest.raises(ProximoError):
        _check_fingerprint(value)


def test_check_no_control_rejects_control_chars():
    with pytest.raises(ProximoError):
        _check_no_control("bad\x00value", "key")


def test_check_no_control_accepts_clean_value():
    assert _check_no_control("clean-value", "key") == "clean-value"


def test_check_int_accepts_valid():
    assert _check_int("64", "ttl") == 64


def test_check_int_rejects_non_integer():
    with pytest.raises(ProximoError):
        _check_int("not-an-int", "ttl")


def test_check_controller_options_rejects_reserved():
    with pytest.raises(ProximoError):
        _check_controller_options({"controller": "sneaky", "asn": 65000})


def test_check_controller_options_accepts_real_fields():
    _check_controller_options({"asn": 65000, "peers": "192.0.2.1"})  # no raise


def test_redact_secrets_masks_key_and_token_only():
    out = _redact_secrets({"key": "sekret", "token": "sekret2", "url": "https://x", "name": "n1"})
    assert out == {"key": "[redacted]", "token": "[redacted]", "url": "https://x", "name": "n1"}


def test_redact_secrets_also_masks_url_userinfo():
    """HIGH-2: `_redact_secrets` masks an embedded userinfo credential in `url` too — not
    just the whole-value swap it applies to key/token."""
    out = _redact_secrets({"url": "http://admin:hunter2@pdns.example.com:8080"})
    assert "hunter2" not in out["url"]
    assert "pdns.example.com:8080" in out["url"]


# --- _redact_url_userinfo (HIGH-2 — mirrors pbs_admin.py's _redact_http_proxy 5c/5d shapes) ---


def test_redact_url_userinfo_none_passthrough():
    assert _redact_url_userinfo(None) is None


def test_redact_url_userinfo_no_userinfo_passthrough():
    assert _redact_url_userinfo("http://pdns.example.com:8080") == "http://pdns.example.com:8080"


def test_redact_url_userinfo_masks_simple_credential():
    out = _redact_url_userinfo("http://admin:hunter2@pdns.example.com:8080")
    assert out == "http://[redacted]@pdns.example.com:8080"


def test_redact_url_userinfo_embedded_literal_at_in_password():
    """Wave 5c review Finding 3 shape: a password containing a literal '@' must not leak its
    tail — last-@ rsplit, not first-@."""
    out = _redact_url_userinfo("http://user:p@ssw0rd@pdns.example.com:8080")
    assert out == "http://[redacted]@pdns.example.com:8080"
    assert "ssw0rd" not in out


def test_redact_url_userinfo_ipv6_host_safe():
    out = _redact_url_userinfo("http://user:pass@[2001:db8::1]:8080")
    assert out == "http://[redacted]@[2001:db8::1]:8080"


def test_redact_url_userinfo_no_scheme_passthrough_shape():
    out = _redact_url_userinfo("user:pass@pdns.example.com:8080")
    assert out == "[redacted]@pdns.example.com:8080"


# --- _strip_secrets_at_read (HIGH-1 — mirrors pbs_metrics.py's influxdb_http_get) ---


def test_strip_secrets_at_read_removes_named_field():
    out = _strip_secrets_at_read({"dns": "d1", "key": "sekret"}, "key")
    assert out == {"dns": "d1"}


def test_strip_secrets_at_read_masks_url_userinfo_too():
    out = _strip_secrets_at_read(
        {"dns": "d1", "url": "http://admin:hunter2@pdns.example.com", "key": "sekret"}, "key",
    )
    assert out == {"dns": "d1", "url": "http://[redacted]@pdns.example.com"}


def test_strip_secrets_at_read_no_op_when_field_absent():
    out = _strip_secrets_at_read({"dns": "d1", "type": "powerdns"}, "key")
    assert out == {"dns": "d1", "type": "powerdns"}


# ---------------------------------------------------------------------------
# 2. Controllers — reads
# ---------------------------------------------------------------------------


def test_controllers_list_url():
    api = _rec()
    controllers_list(api)
    assert api.seen["path"] == "/cluster/sdn/controllers"


def test_controllers_list_type_filter():
    api = _rec()
    controllers_list(api, controller_type="bgp")
    assert api.seen["path"] == "/cluster/sdn/controllers?type=bgp"


def test_controllers_list_rejects_bad_type_filter():
    api = _rec()
    with pytest.raises(ProximoError):
        controllers_list(api, controller_type="openvpn")


def test_controller_get_url():
    api = _rec()
    controller_get(api, "ctrl1")
    assert api.seen["path"] == "/cluster/sdn/controllers/ctrl1"


def test_controller_get_pending_running_query():
    api = _rec()
    controller_get(api, "ctrl1", pending=True, running=False)
    assert api.seen["path"] == "/cluster/sdn/controllers/ctrl1?pending=1&running=0"


def test_controllers_list_empty_defaults_to_list():
    api = _rec()
    out = controllers_list(api)
    assert out == []


def test_controller_get_empty_defaults_to_dict():
    api = _rec()
    out = controller_get(api, "ctrl1")
    assert out == {}


# ---------------------------------------------------------------------------
# 2b. Controllers — mutations
# ---------------------------------------------------------------------------


def test_controller_create_posts_type_and_options():
    api = _rec()
    controller_create(api, "ctrl1", "bgp", options={"asn": 65000})
    assert api.seen["method"] == "POST"
    assert api.seen["path"] == "/cluster/sdn/controllers"
    assert api.seen["data"] == {"type": "bgp", "controller": "ctrl1", "asn": 65000}


def test_controller_create_with_lock_token():
    api = _rec()
    controller_create(api, "ctrl1", "evpn", lock_token="tok1")
    assert api.seen["data"] == {"type": "evpn", "controller": "ctrl1", "lock-token": "tok1"}


def test_controller_create_rejects_reserved_key_in_options():
    api = _rec()
    with pytest.raises(ProximoError):
        controller_create(api, "ctrl1", "bgp", options={"controller": "sneaky"})


def test_controller_update_puts_options():
    api = _rec()
    controller_update(api, "ctrl1", options={"asn": 65001})
    assert api.seen["method"] == "PUT"
    assert api.seen["path"] == "/cluster/sdn/controllers/ctrl1"
    assert api.seen["data"] == {"asn": 65001}


def test_controller_update_delete_csv():
    api = _rec()
    controller_update(api, "ctrl1", delete=["asn", "peers"])
    assert api.seen["data"] == {"delete": "asn,peers"}


def test_controller_update_digest_and_lock_token():
    api = _rec()
    controller_update(api, "ctrl1", options={"asn": 1}, digest="d1", lock_token="t1")
    assert api.seen["data"] == {"asn": 1, "digest": "d1", "lock-token": "t1"}


def test_controller_update_requires_something():
    api = _rec()
    with pytest.raises(ProximoError):
        controller_update(api, "ctrl1")


def test_controller_update_never_forwards_type():
    """type is IMMUTABLE — controller_update has no `type`/`controller_type` param at all."""
    import inspect
    assert "controller_type" not in inspect.signature(controller_update).parameters
    assert "type" not in inspect.signature(controller_update).parameters


def test_controller_delete_no_digest():
    api = _rec()
    controller_delete(api, "ctrl1")
    assert api.seen["method"] == "DELETE"
    assert api.seen["path"] == "/cluster/sdn/controllers/ctrl1"
    assert api.seen["params"] == {}


def test_controller_delete_with_lock_token():
    api = _rec()
    controller_delete(api, "ctrl1", lock_token="tok1")
    assert api.seen["params"] == {"lock-token": "tok1"}


# ---------------------------------------------------------------------------
# 3. DNS — reads
# ---------------------------------------------------------------------------


def test_dns_list_url():
    api = _rec()
    dns_list(api)
    assert api.seen["path"] == "/cluster/sdn/dns"


def test_dns_list_type_filter():
    api = _rec()
    dns_list(api, dns_type="powerdns")
    assert api.seen["path"] == "/cluster/sdn/dns?type=powerdns"


def test_dns_get_url_no_query_params():
    """dns_get has NO pending/running (unlike controller_get) — module docstring fact #3."""
    api = _rec()
    dns_get(api, "dns1")
    assert api.seen["path"] == "/cluster/sdn/dns/dns1"


def test_dns_get_strips_key_at_read_layer():
    """THE REINSTATED RULING: dns_get strips `key` at the read layer (removed entirely, not
    masked) — mirrors pbs_metrics.py's influxdb_http_get mechanism exactly."""
    api = _rec()
    api.seen["_get_return"] = {"dns": "dns1", "type": "powerdns", "key": "leaked-raw-key"}
    out = dns_get(api, "dns1")
    assert "key" not in out
    assert "leaked-raw-key" not in str(out)


def test_dns_get_non_secret_fields_survive_the_strip_untouched():
    api = _rec()
    api.seen["_get_return"] = {"dns": "dns1", "type": "powerdns", "ttl": 300, "key": "leaked"}
    out = dns_get(api, "dns1")
    assert out == {"dns": "dns1", "type": "powerdns", "ttl": 300}


def test_dns_get_masks_url_userinfo():
    api = _rec()
    api.seen["_get_return"] = {
        "dns": "dns1", "url": "http://admin:hunter2@pdns.example.com:8080",
    }
    out = dns_get(api, "dns1")
    assert "hunter2" not in out["url"]
    assert "pdns.example.com:8080" in out["url"]


def test_dns_get_url_without_userinfo_passes_through_unchanged():
    api = _rec()
    api.seen["_get_return"] = {"dns": "dns1", "url": "https://pdns.example.com"}
    out = dns_get(api, "dns1")
    assert out["url"] == "https://pdns.example.com"


# ---------------------------------------------------------------------------
# 3b. DNS — mutations
# ---------------------------------------------------------------------------


def test_dns_create_posts_required_fields():
    api = _rec()
    dns_create(api, "dns1", "powerdns", "https://pdns.example.com", "sekret-key")
    assert api.seen["method"] == "POST"
    assert api.seen["path"] == "/cluster/sdn/dns"
    assert api.seen["data"] == {
        "type": "powerdns", "dns": "dns1", "url": "https://pdns.example.com", "key": "sekret-key",
    }


def test_dns_create_all_optional_fields():
    api = _rec()
    dns_create(
        api, "dns1", "powerdns", "https://pdns.example.com", "sekret-key",
        fingerprint=FINGERPRINT, reversemaskv6=64, reversev6mask=32, dns_ttl=300,
        lock_token="tok1",
    )
    assert api.seen["data"] == {
        "type": "powerdns", "dns": "dns1", "url": "https://pdns.example.com", "key": "sekret-key",
        "fingerprint": FINGERPRINT, "reversemaskv6": 64, "reversev6mask": 32, "ttl": 300,
        "lock-token": "tok1",
    }


def test_dns_create_rejects_bad_type():
    api = _rec()
    with pytest.raises(ProximoError):
        dns_create(api, "dns1", "bind9", "https://x", "k")


def test_dns_create_rejects_control_chars_in_key():
    api = _rec()
    with pytest.raises(ProximoError):
        dns_create(api, "dns1", "powerdns", "https://x", "bad\x00key")


def test_dns_update_puts_only_given_fields():
    api = _rec()
    dns_update(api, "dns1", url="https://new.example.com")
    assert api.seen["method"] == "PUT"
    assert api.seen["path"] == "/cluster/sdn/dns/dns1"
    assert api.seen["data"] == {"url": "https://new.example.com"}


def test_dns_update_has_no_reversev6mask_param():
    """Schema asymmetry (module docstring fact #4): reversev6mask exists on CREATE only."""
    import inspect
    assert "reversev6mask" not in inspect.signature(dns_update).parameters
    assert "reversemaskv6" in inspect.signature(dns_update).parameters


def test_dns_update_key_forwarded_raw_on_wire():
    api = _rec()
    dns_update(api, "dns1", key="new-sekret-key")
    assert api.seen["data"] == {"key": "new-sekret-key"}


def test_dns_update_delete_digest_lock_token():
    api = _rec()
    dns_update(api, "dns1", delete=["ttl"], digest="dgst", lock_token="tok1")
    assert api.seen["data"] == {"delete": "ttl", "digest": "dgst", "lock-token": "tok1"}


def test_dns_update_requires_something():
    api = _rec()
    with pytest.raises(ProximoError):
        dns_update(api, "dns1")


def test_dns_update_never_forwards_type():
    import inspect
    assert "dns_type" not in inspect.signature(dns_update).parameters


def test_dns_delete_no_digest():
    api = _rec()
    dns_delete(api, "dns1")
    assert api.seen["path"] == "/cluster/sdn/dns/dns1"
    assert api.seen["params"] == {}


# ---------------------------------------------------------------------------
# 4. IPAMs — reads
# ---------------------------------------------------------------------------


def test_ipams_list_url():
    api = _rec()
    ipams_list(api)
    assert api.seen["path"] == "/cluster/sdn/ipams"


def test_ipams_list_type_filter():
    api = _rec()
    ipams_list(api, ipam_type="netbox")
    assert api.seen["path"] == "/cluster/sdn/ipams?type=netbox"


def test_ipam_get_url_no_query_params():
    api = _rec()
    ipam_get(api, "ipam1")
    assert api.seen["path"] == "/cluster/sdn/ipams/ipam1"


def test_ipam_get_strips_token_at_read_layer():
    """THE REINSTATED RULING, mirror of dns_get: token is removed entirely, not masked."""
    api = _rec()
    api.seen["_get_return"] = {"ipam": "ipam1", "type": "netbox", "token": "leaked-raw-token"}
    out = ipam_get(api, "ipam1")
    assert "token" not in out
    assert "leaked-raw-token" not in str(out)


def test_ipam_get_non_secret_fields_survive_the_strip_untouched():
    api = _rec()
    api.seen["_get_return"] = {"ipam": "ipam1", "type": "netbox", "section": 3, "token": "leaked"}
    out = ipam_get(api, "ipam1")
    assert out == {"ipam": "ipam1", "type": "netbox", "section": 3}


def test_ipam_get_masks_url_userinfo():
    api = _rec()
    api.seen["_get_return"] = {
        "ipam": "ipam1", "url": "http://admin:hunter2@netbox.example.com:8080",
    }
    out = ipam_get(api, "ipam1")
    assert "hunter2" not in out["url"]
    assert "netbox.example.com:8080" in out["url"]


def test_ipam_get_url_without_userinfo_passes_through_unchanged():
    api = _rec()
    api.seen["_get_return"] = {"ipam": "ipam1", "url": "https://netbox.example.com"}
    out = ipam_get(api, "ipam1")
    assert out["url"] == "https://netbox.example.com"


def test_ipam_status_url():
    api = _rec()
    ipam_status(api, "ipam1")
    assert api.seen["path"] == "/cluster/sdn/ipams/ipam1/status"


def test_ipam_status_empty_defaults_to_list():
    api = _rec()
    out = ipam_status(api, "ipam1")
    assert out == []


# ---------------------------------------------------------------------------
# 4b. IPAMs — mutations
# ---------------------------------------------------------------------------


def test_ipam_create_minimal():
    api = _rec()
    ipam_create(api, "ipam1", "pve")
    assert api.seen["method"] == "POST"
    assert api.seen["path"] == "/cluster/sdn/ipams"
    assert api.seen["data"] == {"type": "pve", "ipam": "ipam1"}


def test_ipam_create_all_fields():
    api = _rec()
    ipam_create(
        api, "ipam1", "netbox", url="https://netbox.example.com", token="sekret-token",
        section=3, fingerprint=FINGERPRINT, lock_token="tok1",
    )
    assert api.seen["data"] == {
        "type": "netbox", "ipam": "ipam1", "url": "https://netbox.example.com",
        "token": "sekret-token", "section": 3, "fingerprint": FINGERPRINT, "lock-token": "tok1",
    }


def test_ipam_create_rejects_bad_type():
    api = _rec()
    with pytest.raises(ProximoError):
        ipam_create(api, "ipam1", "infoblox")


def test_ipam_create_rejects_control_chars_in_token():
    api = _rec()
    with pytest.raises(ProximoError):
        ipam_create(api, "ipam1", "netbox", token="bad\x00token")


def test_ipam_update_only_given_fields():
    api = _rec()
    ipam_update(api, "ipam1", section=5)
    assert api.seen["method"] == "PUT"
    assert api.seen["path"] == "/cluster/sdn/ipams/ipam1"
    assert api.seen["data"] == {"section": 5}


def test_ipam_update_token_forwarded_raw_on_wire():
    api = _rec()
    ipam_update(api, "ipam1", token="new-sekret-token")
    assert api.seen["data"] == {"token": "new-sekret-token"}


def test_ipam_update_delete_digest_lock_token():
    api = _rec()
    ipam_update(api, "ipam1", delete=["token"], digest="dgst", lock_token="tok1")
    assert api.seen["data"] == {"delete": "token", "digest": "dgst", "lock-token": "tok1"}


def test_ipam_update_requires_something():
    api = _rec()
    with pytest.raises(ProximoError):
        ipam_update(api, "ipam1")


def test_ipam_update_never_forwards_type():
    import inspect
    assert "ipam_type" not in inspect.signature(ipam_update).parameters


def test_ipam_delete_no_digest():
    api = _rec()
    ipam_delete(api, "ipam1")
    assert api.seen["path"] == "/cluster/sdn/ipams/ipam1"
    assert api.seen["params"] == {}


# ---------------------------------------------------------------------------
# 5. Plan factories — controllers
# ---------------------------------------------------------------------------


def test_plan_controller_create_is_low():
    plan = plan_controller_create("ctrl1", "bgp", options={"asn": 65000})
    assert plan.risk == RISK_LOW
    assert "ctrl1" in plan.change
    assert any("INERT until pve_sdn_apply" in line for line in plan.blast_radius)


def test_plan_controller_update_is_low_and_requires_something():
    plan = plan_controller_update("ctrl1", options={"asn": 65001})
    assert plan.risk == RISK_LOW
    with pytest.raises(ProximoError):
        plan_controller_update("ctrl1")


def test_plan_controller_delete_is_medium_and_captures_current():
    api = _rec()
    api.seen["_get_return"] = [{"controller": "ctrl1", "type": "bgp"}]
    plan = plan_controller_delete(api, "ctrl1")
    assert plan.risk == RISK_MEDIUM
    assert plan.current == {"controller": "ctrl1", "type": "bgp"}
    assert plan.complete is True
    assert any("Smoke-confirm" in line for line in plan.blast_radius)


def test_plan_controller_delete_read_failed_is_incomplete():
    plan = plan_controller_delete(_boom_api(), "ctrl1")
    assert plan.complete is False
    assert plan.current == {}


# ---------------------------------------------------------------------------
# 5b. Plan factories — dns (the secret-redaction headline)
# ---------------------------------------------------------------------------


def test_plan_dns_create_redacts_key_in_change_text():
    plan = plan_dns_create("dns1", "powerdns", "https://pdns.example.com", "sekret-key")
    assert plan.risk == RISK_LOW
    dumped = json.dumps(plan.as_dict())
    assert "sekret-key" not in dumped
    assert "[redacted]" in dumped
    assert "https://pdns.example.com" in dumped  # url is NOT secret — visible


def test_plan_dns_update_captures_and_redacts_current():
    """`key` is stripped entirely at the read layer (dns_get) — it's absent from
    plan.current, not present as "[redacted]"."""
    api = _rec()
    api.seen["_get_return"] = {"dns": "dns1", "type": "powerdns", "key": "leaked-from-get", "url": "https://x"}
    plan = plan_dns_update(api, "dns1", dns_ttl=300)
    assert "key" not in plan.current
    assert plan.current["url"] == "https://x"
    assert "leaked-from-get" not in str(plan.as_dict())


def test_plan_dns_update_new_key_redacted_in_change_text():
    api = _rec()
    plan = plan_dns_update(api, "dns1", key="new-sekret-key")
    assert "new-sekret-key" not in plan.change
    assert "[redacted]" in plan.change


def test_plan_dns_update_requires_something():
    api = _rec()
    with pytest.raises(ProximoError):
        plan_dns_update(api, "dns1")


def test_plan_dns_create_masks_url_userinfo_in_change_text():
    plan = plan_dns_create(
        "dns1", "powerdns", "http://admin:hunter2@pdns.example.com", "sekret-key",
    )
    dumped = json.dumps(plan.as_dict())
    assert "hunter2" not in dumped
    assert "pdns.example.com" in dumped


def test_plan_dns_update_masks_new_url_userinfo_in_change_text():
    api = _rec()
    plan = plan_dns_update(api, "dns1", url="http://admin:hunter2@pdns.example.com")
    assert "hunter2" not in plan.change
    assert "pdns.example.com" in plan.change


def test_plan_dns_update_captures_and_masks_url_userinfo_in_current():
    api = _rec()
    api.seen["_get_return"] = {
        "dns": "dns1", "url": "http://admin:hunter2@pdns.example.com", "key": "leaked",
    }
    plan = plan_dns_update(api, "dns1", dns_ttl=300)
    assert "hunter2" not in json.dumps(plan.as_dict())
    assert "pdns.example.com" in plan.current["url"]


def test_plan_dns_delete_captures_and_redacts_key():
    """`key` is stripped entirely at the read layer — absent from plan.current."""
    api = _rec()
    api.seen["_get_return"] = {"dns": "dns1", "key": "leaked-from-get"}
    plan = plan_dns_delete(api, "dns1")
    assert plan.risk == RISK_MEDIUM
    assert "key" not in plan.current
    assert "leaked-from-get" not in str(plan.as_dict())


def test_plan_dns_delete_read_failed_is_incomplete():
    plan = plan_dns_delete(_boom_api(), "dns1")
    assert plan.complete is False


# ---------------------------------------------------------------------------
# 5c. Plan factories — ipams (the secret-redaction headline, mirror of dns)
# ---------------------------------------------------------------------------


def test_plan_ipam_create_redacts_token_in_change_text():
    plan = plan_ipam_create("ipam1", "netbox", url="https://netbox.example.com", token="sekret-token")
    assert plan.risk == RISK_LOW
    dumped = json.dumps(plan.as_dict())
    assert "sekret-token" not in dumped
    assert "[redacted]" in dumped
    assert "https://netbox.example.com" in dumped


def test_plan_ipam_update_captures_and_redacts_current():
    """`token` is stripped entirely at the read layer (ipam_get) — absent from
    plan.current, not present as "[redacted]"."""
    api = _rec()
    api.seen["_get_return"] = {"ipam": "ipam1", "type": "netbox", "token": "leaked-from-get", "url": "https://x"}
    plan = plan_ipam_update(api, "ipam1", section=7)
    assert "token" not in plan.current
    assert plan.current["url"] == "https://x"
    assert "leaked-from-get" not in str(plan.as_dict())


def test_plan_ipam_update_new_token_redacted_in_change_text():
    api = _rec()
    plan = plan_ipam_update(api, "ipam1", token="new-sekret-token")
    assert "new-sekret-token" not in plan.change
    assert "[redacted]" in plan.change


def test_plan_ipam_update_requires_something():
    api = _rec()
    with pytest.raises(ProximoError):
        plan_ipam_update(api, "ipam1")


def test_plan_ipam_create_masks_url_userinfo_in_change_text():
    plan = plan_ipam_create(
        "ipam1", "netbox", url="http://admin:hunter2@netbox.example.com", token="sekret-token",
    )
    dumped = json.dumps(plan.as_dict())
    assert "hunter2" not in dumped
    assert "netbox.example.com" in dumped


def test_plan_ipam_update_masks_new_url_userinfo_in_change_text():
    api = _rec()
    plan = plan_ipam_update(api, "ipam1", url="http://admin:hunter2@netbox.example.com")
    assert "hunter2" not in plan.change
    assert "netbox.example.com" in plan.change


def test_plan_ipam_update_captures_and_masks_url_userinfo_in_current():
    api = _rec()
    api.seen["_get_return"] = {
        "ipam": "ipam1", "url": "http://admin:hunter2@netbox.example.com", "token": "leaked",
    }
    plan = plan_ipam_update(api, "ipam1", section=5)
    assert "hunter2" not in json.dumps(plan.as_dict())
    assert "netbox.example.com" in plan.current["url"]


def test_plan_ipam_delete_captures_and_redacts_token():
    """`token` is stripped entirely at the read layer — absent from plan.current."""
    api = _rec()
    api.seen["_get_return"] = {"ipam": "ipam1", "token": "leaked-from-get"}
    plan = plan_ipam_delete(api, "ipam1")
    assert plan.risk == RISK_MEDIUM
    assert "token" not in plan.current
    assert "leaked-from-get" not in str(plan.as_dict())


def test_plan_ipam_delete_read_failed_is_incomplete():
    plan = plan_ipam_delete(_boom_api(), "ipam1")
    assert plan.complete is False
