"""TDD tests for the PBS metrics servers plane (Wave 5b, full-surface campaign) — fully mocked,
no live PBS.

Mirrors test_pbs_s3.py's style: a recording fake PBS API, validator rejection tests (\\Z-anchored),
backend-function path/verb/payload tests, and plan-factory risk/blast-radius tests. Adds the
SECRET CONTRACT tests for `token` (module docstring fact #1: the READ-layer strip is REQUIRED,
not merely defensive — the live schema's response shape DOES carry `token`, unlike pbs_s3's
documented-secret-free reads).

Covers: validators (name, digest, url, host, comment, bucket/organization, positive_int,
start_time); backend functions for all 12 ops (6 read, 6 mutation); plan factories (RISK_MEDIUM
influxdb-http create/update/delete, RISK_LOW influxdb-udp create/update/delete); the
token-redaction contract; module structure.
"""

from __future__ import annotations

import pytest

from proximo.backends import ProximoError
from proximo.pbs_metrics import (
    _check_bucket,
    _check_comment,
    _check_digest,
    _check_host,
    _check_name,
    _check_organization,
    _check_positive_int,
    _check_start_time,
    _check_url,
    _redact_secrets,
    influxdb_http_create,
    influxdb_http_delete,
    influxdb_http_get,
    influxdb_http_list,
    influxdb_http_update,
    influxdb_udp_create,
    influxdb_udp_delete,
    influxdb_udp_get,
    influxdb_udp_list,
    influxdb_udp_update,
    metrics_servers_list,
    metrics_status,
    plan_influxdb_http_create,
    plan_influxdb_http_delete,
    plan_influxdb_http_update,
    plan_influxdb_udp_create,
    plan_influxdb_udp_delete,
    plan_influxdb_udp_update,
)
from proximo.planning import RISK_LOW, RISK_MEDIUM

# ---------------------------------------------------------------------------
# Recording fake
# ---------------------------------------------------------------------------

class _Api:
    """Recording fake for PbsBackend (HTTP verb tracking, no live network)."""

    def __init__(self, get_return=None):
        self._get_return = get_return
        self.gets: list[tuple] = []
        self.posts: list[tuple] = []
        self.puts: list[tuple] = []
        self.dels: list[tuple] = []

    def _get(self, path: str, params=None):
        self.gets.append((path, params))
        return self._get_return

    def _post(self, path: str, data=None):
        self.posts.append((path, data))
        return None

    def _put(self, path: str, data=None):
        self.puts.append((path, data))
        return None

    def _delete(self, path: str, params=None):
        self.dels.append((path, params))
        return None


# ---------------------------------------------------------------------------
# Module structure
# ---------------------------------------------------------------------------

def test_module_docstring_names_schema_facts():
    import proximo.pbs_metrics as m
    doc = m.__doc__ or ""
    assert "token" in doc.lower()
    assert "influxdb-http" in doc.lower()
    assert "influxdb-udp" in doc.lower()


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

class TestCheckName:
    def test_valid_simple(self):
        assert _check_name("metrics1") == "metrics1"

    def test_valid_with_dot_underscore_hyphen(self):
        assert _check_name("m-1.a_2") == "m-1.a_2"

    def test_min_length_three_enforced(self):
        with pytest.raises(ProximoError):
            _check_name("ab")

    def test_min_length_three_accepted(self):
        assert _check_name("abc") == "abc"

    def test_max_length_32_enforced(self):
        with pytest.raises(ProximoError):
            _check_name("a" * 33)

    def test_max_length_32_accepted(self):
        assert _check_name("a" * 32) == "a" * 32

    def test_slash_raises(self):
        with pytest.raises(ProximoError):
            _check_name("name/slash")

    def test_trailing_newline_raises(self):
        with pytest.raises(ProximoError):
            _check_name("metrics\n")

    def test_empty_raises(self):
        with pytest.raises(ProximoError):
            _check_name("")

    def test_leading_dot_rejected(self):
        with pytest.raises(ProximoError):
            _check_name(".metrics")


class TestCheckDigest:
    def test_valid(self):
        d = "a" * 64
        assert _check_digest(d) == d

    def test_uppercase_hex_rejected(self):
        with pytest.raises(ProximoError):
            _check_digest("A" * 64)

    def test_wrong_length_rejected(self):
        with pytest.raises(ProximoError):
            _check_digest("a" * 63)


class TestCheckUrl:
    def test_hostname_with_port_accepted(self):
        assert _check_url("https://influx.example.com:8086") == "https://influx.example.com:8086"

    def test_http_scheme_accepted(self):
        assert _check_url("http://192.168.1.1") == "http://192.168.1.1"

    def test_ipv6_accepted(self):
        assert _check_url("https://[2001:db8::1]:8086") == "https://[2001:db8::1]:8086"

    def test_path_accepted(self):
        assert _check_url("https://example.com:8086/write") == "https://example.com:8086/write"

    def test_no_port_accepted(self):
        assert _check_url("https://example.com") == "https://example.com"

    def test_ftp_scheme_rejected(self):
        with pytest.raises(ProximoError):
            _check_url("ftp://example.com")

    def test_no_scheme_rejected(self):
        with pytest.raises(ProximoError):
            _check_url("example.com")

    def test_trailing_newline_rejected(self):
        with pytest.raises(ProximoError):
            _check_url("https://example.com\n")


class TestCheckHost:
    def test_hostname_with_port_accepted(self):
        assert _check_host("influx.example.com:8089") == "influx.example.com:8089"

    def test_ipv4_with_port_accepted(self):
        assert _check_host("192.168.1.1:8089") == "192.168.1.1:8089"

    def test_ipv6_with_port_accepted(self):
        assert _check_host("[2001:db8::1]:8089") == "[2001:db8::1]:8089"

    def test_missing_port_rejected(self):
        """Unlike `url` (optional port), `host` REQUIRES a trailing :port on every verb
        (module docstring fact re: _HOST_RE) — confirmed on GET/POST/PUT alike."""
        with pytest.raises(ProximoError):
            _check_host("192.168.1.1")

    def test_missing_port_hostname_rejected(self):
        with pytest.raises(ProximoError):
            _check_host("example.com")

    def test_trailing_newline_rejected(self):
        with pytest.raises(ProximoError):
            _check_host("192.168.1.1:8089\n")


class TestCheckComment:
    def test_valid(self):
        assert _check_comment("a nice comment") == "a nice comment"

    def test_over_128_rejected(self):
        with pytest.raises(ProximoError):
            _check_comment("a" * 129)

    def test_control_char_rejected(self):
        with pytest.raises(ProximoError):
            _check_comment("bad\x00comment")

    def test_empty_allowed(self):
        assert _check_comment("") == ""


class TestCheckBucketOrganization:
    def test_bucket_valid(self):
        assert _check_bucket("mybucket") == "mybucket"

    def test_bucket_empty_rejected(self):
        with pytest.raises(ProximoError):
            _check_bucket("")

    def test_bucket_over_32_rejected(self):
        with pytest.raises(ProximoError):
            _check_bucket("a" * 33)

    def test_bucket_control_char_rejected(self):
        with pytest.raises(ProximoError):
            _check_bucket("bad\x01bucket")

    def test_organization_valid(self):
        assert _check_organization("myorg") == "myorg"

    def test_organization_empty_rejected(self):
        with pytest.raises(ProximoError):
            _check_organization("")

    def test_organization_over_32_rejected(self):
        with pytest.raises(ProximoError):
            _check_organization("a" * 33)


class TestCheckPositiveInt:
    def test_valid(self):
        assert _check_positive_int(1500, "mtu") == 1500

    def test_zero_rejected(self):
        with pytest.raises(ProximoError):
            _check_positive_int(0, "mtu")

    def test_negative_rejected(self):
        with pytest.raises(ProximoError):
            _check_positive_int(-1, "mtu")

    def test_non_integer_rejected(self):
        with pytest.raises(ProximoError):
            _check_positive_int("not-an-int", "mtu")

    def test_no_invented_upper_bound(self):
        """Module docstring fact #10: the schema states NO upper bound for mtu/max-body-size —
        a very large value is still accepted (no ceiling invented)."""
        assert _check_positive_int(10_000_000_000, "max_body_size") == 10_000_000_000


class TestCheckStartTime:
    def test_valid(self):
        assert _check_start_time(1700000000) == 1700000000

    def test_zero_accepted(self):
        assert _check_start_time(0) == 0

    def test_non_integer_rejected(self):
        with pytest.raises(ProximoError):
            _check_start_time("not-an-int")


class TestRedactSecrets:
    def test_token_redacted(self):
        out = _redact_secrets({"token": "sekrit", "name": "met1"})
        assert out["token"] == "[redacted]"

    def test_non_secret_untouched(self):
        out = _redact_secrets({"bucket": "proxmox", "port": 8086})
        assert out["bucket"] == "proxmox"
        assert out["port"] == 8086


# ---------------------------------------------------------------------------
# Backend functions — reads, cross-plane
# ---------------------------------------------------------------------------

class TestMetricsServersList:
    def test_calls_correct_path(self):
        api = _Api(get_return=[{"name": "met1", "type": "influxdb-http", "server": "x"}])
        result = metrics_servers_list(api)
        assert api.gets == [("/admin/metrics", None)]
        assert result[0]["name"] == "met1"

    def test_empty_api_returns_empty_list(self):
        api = _Api(get_return=None)
        assert metrics_servers_list(api) == []


class TestMetricsStatus:
    def test_calls_correct_path_with_defaults(self):
        api = _Api(get_return={"data": []})
        result = metrics_status(api)
        assert api.gets == [("/status/metrics", {"history": False})]
        assert result == {"data": []}

    def test_history_forwarded(self):
        api = _Api(get_return={})
        metrics_status(api, history=True)
        assert api.gets == [("/status/metrics", {"history": True})]

    def test_start_time_forwarded(self):
        api = _Api(get_return={})
        metrics_status(api, start_time=1700000000)
        assert api.gets == [("/status/metrics", {"history": False, "start-time": 1700000000})]

    def test_none_returns_empty_dict(self):
        api = _Api(get_return=None)
        assert metrics_status(api) == {}


# ---------------------------------------------------------------------------
# Backend functions — reads, influxdb-http
# ---------------------------------------------------------------------------

class TestInfluxdbHttpList:
    def test_calls_correct_path(self):
        api = _Api(get_return=[{"name": "met1", "url": "https://x:8086"}])
        result = influxdb_http_list(api)
        assert api.gets == [("/config/metrics/influxdb-http", None)]
        assert result[0]["name"] == "met1"

    def test_empty_api_returns_empty_list(self):
        api = _Api(get_return=None)
        assert influxdb_http_list(api) == []

    def test_token_stripped_required_not_defensive(self):
        """Module docstring fact #1: token DOES appear in the live schema's response shape — this
        is a REQUIRED strip, not merely defense-in-depth (unlike pbs_s3's documented-secret-free
        reads)."""
        api = _Api(get_return=[{"name": "met1", "token": "sentinel-leaked-token"}])
        result = influxdb_http_list(api)
        assert "token" not in result[0]


class TestInfluxdbHttpGet:
    def test_correct_path(self):
        api = _Api(get_return={"name": "met1"})
        result = influxdb_http_get(api, "met1")
        assert api.gets == [("/config/metrics/influxdb-http/met1", None)]
        assert result["name"] == "met1"

    def test_token_stripped(self):
        api = _Api(get_return={"name": "met1", "token": "sentinel-leaked-token"})
        result = influxdb_http_get(api, "met1")
        assert "token" not in result

    def test_invalid_name_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            influxdb_http_get(api, "ab")


# ---------------------------------------------------------------------------
# Backend functions — mutations, influxdb-http
# ---------------------------------------------------------------------------

class TestInfluxdbHttpCreate:
    def test_posts_minimal_required_fields(self):
        api = _Api()
        influxdb_http_create(api, "met1", "https://influx.example.com:8086")
        assert len(api.posts) == 1
        path, data = api.posts[0]
        assert path == "/config/metrics/influxdb-http"
        assert data == {"name": "met1", "url": "https://influx.example.com:8086"}

    def test_all_optional_fields_forwarded(self):
        api = _Api()
        influxdb_http_create(
            api, "met1", "https://influx.example.com:8086",
            bucket="mybucket", comment="a comment", enable=True, max_body_size=1000,
            organization="myorg", token="sentinel-token-value", verify_tls=False,
        )
        _, data = api.posts[0]
        assert data["bucket"] == "mybucket"
        assert data["comment"] == "a comment"
        assert data["enable"] is True
        assert data["max-body-size"] == 1000
        assert data["organization"] == "myorg"
        assert data["token"] == "sentinel-token-value"
        assert data["verify-tls"] is False

    def test_invalid_name_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            influxdb_http_create(api, "ab", "https://influx.example.com:8086")

    def test_invalid_url_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            influxdb_http_create(api, "met1", "not-a-url")

    def test_control_char_in_token_rejected(self):
        api = _Api()
        with pytest.raises(ProximoError):
            influxdb_http_create(api, "met1", "https://x:8086", token="bad\x00token")


class TestInfluxdbHttpUpdate:
    def test_puts_to_correct_path(self):
        api = _Api()
        influxdb_http_update(api, "met1", bucket="newbucket")
        assert len(api.puts) == 1
        path, data = api.puts[0]
        assert path == "/config/metrics/influxdb-http/met1"
        assert data == {"bucket": "newbucket"}

    def test_none_kwargs_excluded(self):
        api = _Api()
        influxdb_http_update(api, "met1")
        _, data = api.puts[0]
        assert data == {}

    def test_digest_forwarded(self):
        api = _Api()
        influxdb_http_update(api, "met1", digest="a" * 64)
        _, data = api.puts[0]
        assert data["digest"] == "a" * 64

    def test_delete_list_forwarded(self):
        api = _Api()
        influxdb_http_update(api, "met1", delete=["token", "bucket"])
        _, data = api.puts[0]
        assert data["delete"] == ["token", "bucket"]

    def test_token_rotation_forwarded(self):
        api = _Api()
        influxdb_http_update(api, "met1", token="sentinel-new-token")
        _, data = api.puts[0]
        assert data["token"] == "sentinel-new-token"

    def test_name_never_in_body(self):
        """Module docstring fact #7: `name` is the PATH parameter — never duplicated in the PUT
        body, matching pbs_s3.py's own s3_client_update convention."""
        api = _Api()
        influxdb_http_update(api, "met1", bucket="newbucket")
        _, data = api.puts[0]
        assert "name" not in data

    def test_invalid_name_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            influxdb_http_update(api, "ab")


class TestInfluxdbHttpDelete:
    def test_deletes_correct_path(self):
        api = _Api()
        influxdb_http_delete(api, "met1")
        assert api.dels[0][0] == "/config/metrics/influxdb-http/met1"
        assert api.dels[0][1] == {}

    def test_digest_forwarded(self):
        api = _Api()
        influxdb_http_delete(api, "met1", digest="c" * 64)
        assert api.dels[0][1] == {"digest": "c" * 64}

    def test_invalid_name_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            influxdb_http_delete(api, "ab")


# ---------------------------------------------------------------------------
# Backend functions — reads, influxdb-udp
# ---------------------------------------------------------------------------

class TestInfluxdbUdpList:
    def test_calls_correct_path(self):
        api = _Api(get_return=[{"name": "udp1", "host": "192.0.2.1:8089"}])
        result = influxdb_udp_list(api)
        assert api.gets == [("/config/metrics/influxdb-udp", None)]
        assert result[0]["name"] == "udp1"

    def test_no_secret_stripping_applied(self):
        """Module docstring fact #2: no secret field exists on this sub-plane at all — the
        function does not strip anything (there's nothing to strip)."""
        api = _Api(get_return=[{"name": "udp1", "host": "192.0.2.1:8089", "mtu": 1500}])
        result = influxdb_udp_list(api)
        assert result[0] == {"name": "udp1", "host": "192.0.2.1:8089", "mtu": 1500}


class TestInfluxdbUdpGet:
    def test_correct_path(self):
        api = _Api(get_return={"name": "udp1"})
        result = influxdb_udp_get(api, "udp1")
        assert api.gets == [("/config/metrics/influxdb-udp/udp1", None)]
        assert result["name"] == "udp1"

    def test_invalid_name_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            influxdb_udp_get(api, "ab")


# ---------------------------------------------------------------------------
# Backend functions — mutations, influxdb-udp
# ---------------------------------------------------------------------------

class TestInfluxdbUdpCreate:
    def test_posts_minimal_required_fields(self):
        api = _Api()
        influxdb_udp_create(api, "udp1", "192.0.2.1:8089")
        assert len(api.posts) == 1
        path, data = api.posts[0]
        assert path == "/config/metrics/influxdb-udp"
        assert data == {"name": "udp1", "host": "192.0.2.1:8089"}

    def test_all_optional_fields_forwarded(self):
        api = _Api()
        influxdb_udp_create(api, "udp1", "192.0.2.1:8089", comment="a comment", enable=True, mtu=9000)
        _, data = api.posts[0]
        assert data["comment"] == "a comment"
        assert data["enable"] is True
        assert data["mtu"] == 9000

    def test_invalid_name_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            influxdb_udp_create(api, "ab", "192.0.2.1:8089")

    def test_invalid_host_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            influxdb_udp_create(api, "udp1", "192.0.2.1")  # missing port

    def test_no_token_param_exists(self):
        """Module docstring fact #2: no secret field exists on this sub-plane at all — the
        function signature doesn't even accept one."""
        import inspect
        sig = inspect.signature(influxdb_udp_create)
        assert "token" not in sig.parameters


class TestInfluxdbUdpUpdate:
    def test_puts_to_correct_path(self):
        api = _Api()
        influxdb_udp_update(api, "udp1", mtu=9000)
        assert len(api.puts) == 1
        path, data = api.puts[0]
        assert path == "/config/metrics/influxdb-udp/udp1"
        assert data == {"mtu": 9000}

    def test_none_kwargs_excluded(self):
        api = _Api()
        influxdb_udp_update(api, "udp1")
        _, data = api.puts[0]
        assert data == {}

    def test_digest_forwarded(self):
        api = _Api()
        influxdb_udp_update(api, "udp1", digest="a" * 64)
        _, data = api.puts[0]
        assert data["digest"] == "a" * 64

    def test_delete_list_forwarded(self):
        api = _Api()
        influxdb_udp_update(api, "udp1", delete=["mtu", "comment"])
        _, data = api.puts[0]
        assert data["delete"] == ["mtu", "comment"]

    def test_host_rotation_forwarded(self):
        api = _Api()
        influxdb_udp_update(api, "udp1", host="192.0.2.2:9000")
        _, data = api.puts[0]
        assert data["host"] == "192.0.2.2:9000"

    def test_invalid_name_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            influxdb_udp_update(api, "ab")


class TestInfluxdbUdpDelete:
    def test_deletes_correct_path(self):
        api = _Api()
        influxdb_udp_delete(api, "udp1")
        assert api.dels[0][0] == "/config/metrics/influxdb-udp/udp1"
        assert api.dels[0][1] == {}

    def test_digest_forwarded(self):
        api = _Api()
        influxdb_udp_delete(api, "udp1", digest="d" * 64)
        assert api.dels[0][1] == {"digest": "d" * 64}

    def test_invalid_name_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            influxdb_udp_delete(api, "ab")


# ---------------------------------------------------------------------------
# Plan factories — influxdb-http
# ---------------------------------------------------------------------------

class TestPlanInfluxdbHttpCreate:
    def test_is_medium_risk(self):
        plan = plan_influxdb_http_create("met1", "https://x:8086")
        assert plan.risk == RISK_MEDIUM

    def test_target_correct(self):
        plan = plan_influxdb_http_create("met1", "https://x:8086")
        assert plan.target == "pbs/config/metrics/influxdb-http/met1"

    def test_current_is_empty(self):
        plan = plan_influxdb_http_create("met1", "https://x:8086")
        assert plan.current == {}

    def test_token_never_in_change(self):
        plan = plan_influxdb_http_create("met1", "https://x:8086", token="sentinel-token-value")
        assert "sentinel-token-value" not in plan.change

    def test_invalid_name_raises(self):
        with pytest.raises(ProximoError):
            plan_influxdb_http_create("ab", "https://x:8086")

    def test_invalid_url_raises(self):
        with pytest.raises(ProximoError):
            plan_influxdb_http_create("met1", "not-a-url")


class TestPlanInfluxdbHttpUpdate:
    def test_reads_current_from_api(self):
        api = _Api(get_return={"name": "met1", "bucket": "old"})
        plan = plan_influxdb_http_update(api, "met1", bucket="new")
        assert plan.risk == RISK_MEDIUM
        assert plan.current == {"name": "met1", "bucket": "old"}

    def test_no_fields_changed_message(self):
        api = _Api(get_return={"name": "met1"})
        plan = plan_influxdb_http_update(api, "met1")
        assert "no fields changed" in plan.change

    def test_token_never_in_change(self):
        api = _Api(get_return={"name": "met1"})
        plan = plan_influxdb_http_update(api, "met1", token="sentinel-new-token")
        assert "sentinel-new-token" not in plan.change

    def test_empty_delete_list_rejected(self):
        # Wave 5b review finding 1: delete=[] used to be DISCLOSED in the plan on the theory
        # that it's "a real wire payload the execute side sends" — false. httpx's form encoding
        # drops an empty-list value entirely, so it never reaches the wire. Reject loudly
        # instead of disclosing a payload confirm=True would never actually send.
        api = _Api(get_return={"name": "met1"})
        with pytest.raises(ProximoError):
            plan_influxdb_http_update(api, "met1", delete=[])

    def test_captured_current_defensively_redacted_even_when_token_bearing(self):
        """Belt-and-suspenders: even though influxdb_http_get already strips token at the READ
        layer, the plan factory redacts AGAIN — if a future regression removed the read-layer
        strip, this second layer still holds."""
        api = _Api(get_return={"name": "met1", "token": "sentinel-leaked-token"})
        plan = plan_influxdb_http_update(api, "met1", bucket="new")
        assert "token" not in plan.current  # stripped at the read layer
        assert "sentinel-leaked-token" not in str(plan.current)

    def test_invalid_name_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            plan_influxdb_http_update(api, "ab")


class TestPlanInfluxdbHttpDelete:
    def test_is_medium_risk(self):
        api = _Api(get_return={"name": "met1"})
        plan = plan_influxdb_http_delete(api, "met1")
        assert plan.risk == RISK_MEDIUM

    def test_reads_current_from_api(self):
        api = _Api(get_return={"name": "met1", "bucket": "old"})
        plan = plan_influxdb_http_delete(api, "met1")
        assert plan.current == {"name": "met1", "bucket": "old"}

    def test_captured_current_defensively_redacted(self):
        api = _Api(get_return={"name": "met1", "token": "sentinel-leaked-token"})
        plan = plan_influxdb_http_delete(api, "met1")
        assert "token" not in plan.current

    def test_invalid_name_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            plan_influxdb_http_delete(api, "ab")


# ---------------------------------------------------------------------------
# Plan factories — influxdb-udp
# ---------------------------------------------------------------------------

class TestPlanInfluxdbUdpCreate:
    def test_is_low_risk(self):
        """Matches PVE's pve_metrics_server_set baseline exactly — no credential field exists on
        this sub-plane."""
        plan = plan_influxdb_udp_create("udp1", "192.0.2.1:8089")
        assert plan.risk == RISK_LOW

    def test_target_correct(self):
        plan = plan_influxdb_udp_create("udp1", "192.0.2.1:8089")
        assert plan.target == "pbs/config/metrics/influxdb-udp/udp1"

    def test_current_is_empty(self):
        plan = plan_influxdb_udp_create("udp1", "192.0.2.1:8089")
        assert plan.current == {}

    def test_invalid_name_raises(self):
        with pytest.raises(ProximoError):
            plan_influxdb_udp_create("ab", "192.0.2.1:8089")

    def test_invalid_host_raises(self):
        with pytest.raises(ProximoError):
            plan_influxdb_udp_create("udp1", "192.0.2.1")


class TestPlanInfluxdbUdpUpdate:
    def test_is_low_risk(self):
        api = _Api(get_return={"name": "udp1"})
        plan = plan_influxdb_udp_update(api, "udp1", mtu=9000)
        assert plan.risk == RISK_LOW

    def test_reads_current_from_api(self):
        api = _Api(get_return={"name": "udp1", "mtu": 1500})
        plan = plan_influxdb_udp_update(api, "udp1", mtu=9000)
        assert plan.current == {"name": "udp1", "mtu": 1500}

    def test_invalid_name_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            plan_influxdb_udp_update(api, "ab")


class TestPlanInfluxdbUdpDelete:
    def test_is_low_risk(self):
        api = _Api(get_return={"name": "udp1"})
        plan = plan_influxdb_udp_delete(api, "udp1")
        assert plan.risk == RISK_LOW

    def test_reads_current_from_api(self):
        api = _Api(get_return={"name": "udp1", "host": "192.0.2.1:8089"})
        plan = plan_influxdb_udp_delete(api, "udp1")
        assert plan.current == {"name": "udp1", "host": "192.0.2.1:8089"}

    def test_invalid_name_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            plan_influxdb_udp_delete(api, "ab")
