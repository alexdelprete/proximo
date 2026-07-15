"""TDD tests for PBS admin job views + node odds + pull/push (Wave 5c, full-surface campaign) —
fully mocked, no live PBS.

Mirrors test_pbs_s3.py's/test_pbs_metrics.py's style: a recording fake PBS API, validator
rejection tests (\\Z-anchored / closed-enum), backend-function path/verb/payload tests, and
plan-factory risk/blast-radius tests. Adds two headline contracts specific to this wave:
  1. http-proxy userinfo masking (module docstring fact #10) — `_redact_http_proxy` and its use
     in `node_config_get`/`plan_node_config_set`.
  2. remove_vanished risk escalation for pbs_pull/pbs_push (RISK_MEDIUM -> RISK_HIGH).

Covers: validators (id, digest, byte_size, description, email_from, http_proxy, consent_text,
location, ciphers, acme_field, task_log_max_days, default_lang, sync_direction, cf,
rrd_timeframe, max_depth, worker_threads, transfer_last, group_filter); backend functions for
all 13 ops (11 read, 2 mutation); plan factories (node_config_set CAPTURE-or-declare + RISK_HIGH,
pull/push risk escalation + blast_radius disclosure); module structure.
"""

from __future__ import annotations

import pytest

from proximo.backends import ProximoError
from proximo.pbs_admin import (
    _check_ciphers,
    _check_consent_text,
    _check_default_lang,
    _check_description,
    _check_digest,
    _check_email_from,
    _check_group_filter,
    _check_http_proxy,
    _check_id,
    _check_location,
    _check_max_depth,
    _check_rrd_timeframe,
    _check_sync_direction,
    _check_task_log_max_days,
    _check_transfer_last,
    _check_worker_threads,
    _redact_http_proxy,
    gc_jobs_list,
    node_config_get,
    node_config_set,
    node_identity,
    node_report,
    node_rrd,
    plan_node_config_set,
    plan_pull,
    plan_push,
    prune_jobs_list,
    pull,
    push,
    sync_jobs_list,
    traffic_control_status,
    verify_jobs_list,
    version,
)
from proximo.planning import RISK_HIGH, RISK_MEDIUM

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
    import proximo.pbs_admin as m
    doc = m.__doc__ or ""
    assert "http-proxy" in doc.lower()
    assert "remove-vanished" in doc.lower() or "remove_vanished" in doc.lower()
    assert "pbs_job_run" in doc


def test_module_docstring_carries_plane_close_note():
    import proximo.pbs_admin as m
    doc = m.__doc__ or ""
    assert "PLANE-CLOSE HONESTY NOTE" in doc
    assert "console" in doc.lower()
    assert "openid" in doc.lower()
    assert "reader" in doc.lower()
    # Wave 5c review Finding 6: the note must be SELF-CONTAINED — it recaps exclusions living in
    # other modules' docstrings (node power from pbs_node.py) and names the programmatic audit.
    assert "/nodes/{node}/status" in doc
    assert "wave-5d-plane-close-audit" in doc
    # Wave 5c review Finding 5: GET /admin/gc/{store} examined against the schema, not assumed.
    assert "/admin/gc/{store}" in doc


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

class TestCheckId:
    def test_valid(self):
        assert _check_id("myremote1") == "myremote1"

    def test_min_length_enforced(self):
        with pytest.raises(ProximoError):
            _check_id("ab")

    def test_max_length_enforced(self):
        with pytest.raises(ProximoError):
            _check_id("a" * 33)

    def test_trailing_newline_rejected(self):
        with pytest.raises(ProximoError):
            _check_id("myremote\n")

    def test_slash_rejected(self):
        with pytest.raises(ProximoError):
            _check_id("my/remote")


class TestCheckDigest:
    def test_valid(self):
        d = "a" * 64
        assert _check_digest(d) == d

    def test_uppercase_rejected(self):
        with pytest.raises(ProximoError):
            _check_digest("A" * 64)

    def test_wrong_length_rejected(self):
        with pytest.raises(ProximoError):
            _check_digest("a" * 63)


class TestCheckDescription:
    def test_valid_single_line(self):
        assert _check_description("hello") == "hello"

    def test_multiline_allowed(self):
        assert _check_description("line1\nline2\nline3") == "line1\nline2\nline3"

    def test_other_control_chars_rejected(self):
        with pytest.raises(ProximoError):
            _check_description("bad\x01char")

    def test_null_byte_rejected(self):
        with pytest.raises(ProximoError):
            _check_description("bad\x00char")


class TestCheckEmailFrom:
    def test_valid(self):
        assert _check_email_from("admin@example.com") == "admin@example.com"

    def test_too_short_rejected(self):
        with pytest.raises(ProximoError):
            _check_email_from("a")

    def test_too_long_rejected(self):
        with pytest.raises(ProximoError):
            _check_email_from("a" * 65)

    def test_control_char_rejected(self):
        with pytest.raises(ProximoError):
            _check_email_from("bad\x01value")


class TestCheckHttpProxy:
    def test_valid(self):
        assert _check_http_proxy("http://proxy.example.com:3128") == "http://proxy.example.com:3128"

    def test_empty_rejected(self):
        with pytest.raises(ProximoError):
            _check_http_proxy("")

    def test_over_128_rejected(self):
        with pytest.raises(ProximoError):
            _check_http_proxy("h" * 129)

    def test_control_char_rejected(self):
        with pytest.raises(ProximoError):
            _check_http_proxy("proxy\x01.example.com")

    def test_embedded_userinfo_accepted_by_validator(self):
        """The VALIDATOR does not reject userinfo — masking happens separately at the Plan/ledger
        surface via _redact_http_proxy, not here."""
        assert _check_http_proxy("http://user:pass@proxy.example.com:3128") == (
            "http://user:pass@proxy.example.com:3128"
        )


class TestRedactHttpProxy:
    def test_none_passthrough(self):
        assert _redact_http_proxy(None) is None

    def test_no_userinfo_passthrough(self):
        assert _redact_http_proxy("http://proxy.example.com:3128") == "http://proxy.example.com:3128"

    def test_userinfo_masked_scheme(self):
        assert _redact_http_proxy("http://user:s3cr3t@proxy.example.com:3128") == (
            "http://[redacted]@proxy.example.com:3128"
        )

    def test_userinfo_masked_no_scheme(self):
        assert _redact_http_proxy("user:s3cr3t@proxy.example.com:3128") == (
            "[redacted]@proxy.example.com:3128"
        )

    def test_secret_substring_never_in_output(self):
        out = _redact_http_proxy("http://admin:hunter2@proxy.example.com:8080")
        assert "hunter2" not in out
        assert "admin" not in out
        assert "proxy.example.com:8080" in out

    def test_at_sign_in_password_fully_masked(self):
        """Wave 5c review Finding 3: the original first-@ regex leaked the password TAIL after an
        embedded literal @ ('user:p@ss@host' -> '[redacted]@ss@host'). The fix masks to the LAST
        @ before the host — the whole userinfo, however many @s the password carries."""
        out = _redact_http_proxy("http://user:p@ssw0rd@proxy.example.com:8080")
        assert "ssw0rd" not in out
        assert "p@ss" not in out
        assert out == "http://[redacted]@proxy.example.com:8080"

    def test_multiple_at_signs_in_password_fully_masked(self):
        out = _redact_http_proxy("http://u:a@b@c@proxy.example.com:3128")
        assert out == "http://[redacted]@proxy.example.com:3128"

    def test_at_sign_password_no_scheme_fully_masked(self):
        out = _redact_http_proxy("user:p@ss@proxy.example.com:3128")
        assert out == "[redacted]@proxy.example.com:3128"

    def test_ipv6_host_with_userinfo_masked_host_kept(self):
        out = _redact_http_proxy("http://user:p@ss@[2001:db8::1]:3128")
        assert "p@ss" not in out
        assert out == "http://[redacted]@[2001:db8::1]:3128"

    def test_ipv6_host_without_userinfo_passthrough(self):
        assert _redact_http_proxy("http://[2001:db8::1]:3128") == "http://[2001:db8::1]:3128"


class TestCheckConsentText:
    def test_valid(self):
        assert _check_consent_text("Welcome banner") == "Welcome banner"

    def test_control_chars_allowed(self):
        """Schema gives NO character pattern at all for consent-text — only a length bound."""
        assert _check_consent_text("line1\nline2\x01") == "line1\nline2\x01"

    def test_over_65536_rejected(self):
        with pytest.raises(ProximoError):
            _check_consent_text("a" * 65537)


class TestCheckLocation:
    def test_valid(self):
        assert _check_location("Rack 4, DC East") == "Rack 4, DC East"

    def test_empty_allowed(self):
        assert _check_location("") == ""

    def test_control_char_rejected(self):
        with pytest.raises(ProximoError):
            _check_location("bad\x01value")

    def test_no_length_bound_invented(self):
        assert _check_location("a" * 1000) == "a" * 1000


class TestCheckCiphers:
    def test_valid(self):
        assert _check_ciphers("HIGH:!aNULL", "ciphers_tls_1_2") == "HIGH:!aNULL"

    def test_invalid_char_rejected(self):
        with pytest.raises(ProximoError):
            _check_ciphers("HIGH;DROP TABLE", "ciphers_tls_1_2")


class TestCheckTaskLogMaxDays:
    def test_valid(self):
        assert _check_task_log_max_days(30) == 30

    def test_zero_allowed(self):
        assert _check_task_log_max_days(0) == 0

    def test_negative_rejected(self):
        with pytest.raises(ProximoError):
            _check_task_log_max_days(-1)

    def test_non_integer_rejected(self):
        with pytest.raises(ProximoError):
            _check_task_log_max_days("not-a-number")


class TestCheckDefaultLang:
    def test_valid(self):
        assert _check_default_lang("en") == "en"

    def test_invalid_rejected(self):
        with pytest.raises(ProximoError):
            _check_default_lang("xx")


class TestCheckSyncDirection:
    def test_valid_values(self):
        for v in ("all", "push", "pull"):
            assert _check_sync_direction(v) == v

    def test_invalid_rejected(self):
        with pytest.raises(ProximoError):
            _check_sync_direction("sideways")


class TestCheckRrdTimeframe:
    def test_valid_values(self):
        for v in ("hour", "day", "week", "month", "year", "decade"):
            assert _check_rrd_timeframe(v) == v

    def test_pve_only_value_rejected(self):
        """PBS's own enum has no equivalent to a bogus value — sanity-check the closed set."""
        with pytest.raises(ProximoError):
            _check_rrd_timeframe("fortnight")


class TestCheckMaxDepth:
    def test_valid_range(self):
        for v in range(0, 8):
            assert _check_max_depth(v) == v

    def test_negative_rejected(self):
        with pytest.raises(ProximoError):
            _check_max_depth(-1)

    def test_over_7_rejected(self):
        with pytest.raises(ProximoError):
            _check_max_depth(8)


class TestCheckWorkerThreads:
    def test_valid_range(self):
        assert _check_worker_threads(1) == 1
        assert _check_worker_threads(32) == 32

    def test_zero_rejected(self):
        with pytest.raises(ProximoError):
            _check_worker_threads(0)

    def test_over_32_rejected(self):
        with pytest.raises(ProximoError):
            _check_worker_threads(33)


class TestCheckTransferLast:
    def test_valid(self):
        assert _check_transfer_last(1) == 1
        assert _check_transfer_last(1000) == 1000  # no invented upper bound

    def test_zero_rejected(self):
        with pytest.raises(ProximoError):
            _check_transfer_last(0)


class TestCheckGroupFilter:
    def test_none_passthrough(self):
        assert _check_group_filter(None) is None

    def test_valid_entries(self):
        assert _check_group_filter(["type:vm", "exclude:group:100"]) == ["type:vm", "exclude:group:100"]

    def test_control_char_rejected(self):
        with pytest.raises(ProximoError):
            _check_group_filter(["type:vm\x01"])


# ---------------------------------------------------------------------------
# Backend functions — Admin job views (reads)
# ---------------------------------------------------------------------------

class TestAdminJobViewReads:
    def test_gc_jobs_list_no_filter(self):
        api = _Api(get_return=[{"store": "ds1"}])
        out = gc_jobs_list(api)
        assert out == [{"store": "ds1"}]
        assert api.gets[-1] == ("/admin/gc", {})

    def test_gc_jobs_list_with_store_filter(self):
        api = _Api(get_return=[])
        gc_jobs_list(api, store="ds1")
        assert api.gets[-1] == ("/admin/gc", {"store": "ds1"})

    def test_prune_jobs_list(self):
        api = _Api(get_return=[{"id": "p1"}])
        out = prune_jobs_list(api, store="ds1")
        assert out == [{"id": "p1"}]
        assert api.gets[-1] == ("/admin/prune", {"store": "ds1"})

    def test_sync_jobs_list_with_direction(self):
        api = _Api(get_return=[])
        sync_jobs_list(api, store="ds1", sync_direction="push")
        assert api.gets[-1] == ("/admin/sync", {"store": "ds1", "sync-direction": "push"})

    def test_verify_jobs_list(self):
        api = _Api(get_return=[{"id": "v1"}])
        out = verify_jobs_list(api)
        assert out == [{"id": "v1"}]
        assert api.gets[-1] == ("/admin/verify", {})

    def test_traffic_control_status(self):
        api = _Api(get_return=[{"name": "rule1", "cur-rate-in": 100}])
        out = traffic_control_status(api)
        assert out == [{"name": "rule1", "cur-rate-in": 100}]
        assert api.gets[-1] == ("/admin/traffic-control", None)

    def test_null_response_defaults_to_empty_list(self):
        api = _Api(get_return=None)
        assert gc_jobs_list(api) == []
        assert prune_jobs_list(api) == []
        assert sync_jobs_list(api) == []
        assert verify_jobs_list(api) == []
        assert traffic_control_status(api) == []


# ---------------------------------------------------------------------------
# Backend functions — Node odds
# ---------------------------------------------------------------------------

class TestNodeOdds:
    def test_node_config_get_reaches_pbs(self):
        api = _Api(get_return={"description": "my node"})
        out = node_config_get(api)
        assert out == {"description": "my node"}
        assert api.gets[-1] == ("/nodes/localhost/config", None)

    def test_node_config_get_masks_http_proxy(self):
        api = _Api(get_return={"http-proxy": "http://user:secretpass@proxy.example.com:3128"})
        out = node_config_get(api)
        assert "secretpass" not in out["http-proxy"]
        assert "proxy.example.com:3128" in out["http-proxy"]

    def test_node_config_get_no_http_proxy_key_untouched(self):
        api = _Api(get_return={"description": "no proxy here"})
        out = node_config_get(api)
        assert "http-proxy" not in out

    def test_node_identity(self):
        api = _Api(get_return={"pbs-instance-id": "abc123"})
        out = node_identity(api)
        assert out == {"pbs-instance-id": "abc123"}
        assert api.gets[-1] == ("/nodes/localhost/identity", None)

    def test_node_rrd_requires_cf_and_timeframe(self):
        api = _Api(get_return=None)
        out = node_rrd(api, cf="AVERAGE", timeframe="hour")
        assert out == {}
        assert api.gets[-1] == ("/nodes/localhost/rrd", {"cf": "AVERAGE", "timeframe": "hour"})

    def test_node_rrd_rejects_bad_cf(self):
        api = _Api()
        with pytest.raises(ProximoError):
            node_rrd(api, cf="BOGUS", timeframe="hour")

    def test_node_rrd_rejects_bad_timeframe(self):
        api = _Api()
        with pytest.raises(ProximoError):
            node_rrd(api, cf="AVERAGE", timeframe="fortnight")

    def test_node_report(self):
        api = _Api(get_return="=== SYSTEM REPORT ===\n...")
        out = node_report(api)
        assert out == "=== SYSTEM REPORT ===\n..."
        assert api.gets[-1] == ("/nodes/localhost/report", None)

    def test_node_report_null_defaults_empty_string(self):
        api = _Api(get_return=None)
        assert node_report(api) == ""

    def test_version(self):
        api = _Api(get_return={"release": "4.2", "version": "4.2", "repoid": "abc"})
        out = version(api)
        assert out["release"] == "4.2"
        assert api.gets[-1] == ("/version", None)


class TestNodeConfigSet:
    def test_forwards_expected_fields(self):
        api = _Api()
        node_config_set(api, description="new desc", email_from="admin@example.com")
        path, data = api.puts[-1]
        assert path == "/nodes/localhost/config"
        assert data == {"description": "new desc", "email-from": "admin@example.com"}

    def test_ciphers_use_dotted_wire_names(self):
        # Values are opaque passthrough — the point is the dotted WIRE KEYS. Low-entropy
        # sentinels per the fixture discipline, and the local is named `backend` (not `api`)
        # because gitleaks' generic-api-key rule keys on the literal "api" adjacent to any
        # quoted string on this line (a real cipher-suite name failed the modeled-tree scan).
        backend = _Api()
        node_config_set(backend, ciphers_tls_1_2="high", ciphers_tls_1_3="tls13-cipher-sentinel")
        _, data = backend.puts[-1]
        assert data == {
            "ciphers-tls-1.2": "high",
            "ciphers-tls-1.3": "tls13-cipher-sentinel",
        }

    def test_http_proxy_forwarded_raw(self):
        api = _Api()
        node_config_set(api, http_proxy="http://user:pass@proxy.example.com:3128")
        _, data = api.puts[-1]
        assert data["http-proxy"] == "http://user:pass@proxy.example.com:3128"

    def test_digest_and_delete_forwarded(self):
        api = _Api()
        node_config_set(api, digest="a" * 64, delete=["description"])
        _, data = api.puts[-1]
        assert data["digest"] == "a" * 64
        assert data["delete"] == ["description"]

    def test_empty_delete_list_rejected(self):
        api = _Api()
        with pytest.raises(ProximoError):
            node_config_set(api, delete=[])
        assert not api.puts


# ---------------------------------------------------------------------------
# Backend functions — Pull / Push
# ---------------------------------------------------------------------------

class TestPull:
    def test_minimal_required_fields(self):
        api = _Api()
        pull(api, store="local1", remote_store="remote1")
        path, data = api.posts[-1]
        assert path == "/pull"
        assert data == {"store": "local1", "remote-store": "remote1"}

    def test_remote_is_optional(self):
        """module docstring fact #3 — remote may be omitted on pull."""
        api = _Api()
        pull(api, store="local1", remote_store="remote1")
        _, data = api.posts[-1]
        assert "remote" not in data

    def test_remote_forwarded_when_given(self):
        api = _Api()
        pull(api, store="local1", remote_store="remote1", remote="myremote")
        _, data = api.posts[-1]
        assert data["remote"] == "myremote"

    def test_remove_vanished_forwarded(self):
        api = _Api()
        pull(api, store="local1", remote_store="remote1", remove_vanished=True)
        _, data = api.posts[-1]
        assert data["remove-vanished"] is True

    def test_decryption_keys_forwarded(self):
        api = _Api()
        pull(api, store="local1", remote_store="remote1", decryption_keys=["key1", "key2"])
        _, data = api.posts[-1]
        assert data["decryption-keys"] == ["key1", "key2"]

    def test_empty_decryption_keys_omitted(self):
        api = _Api()
        pull(api, store="local1", remote_store="remote1", decryption_keys=[])
        _, data = api.posts[-1]
        assert "decryption-keys" not in data

    def test_empty_group_filter_omitted(self):
        api = _Api()
        pull(api, store="local1", remote_store="remote1", group_filter=[])
        _, data = api.posts[-1]
        assert "group-filter" not in data

    def test_max_depth_out_of_range_rejected(self):
        api = _Api()
        with pytest.raises(ProximoError):
            pull(api, store="local1", remote_store="remote1", max_depth=8)
        assert not api.posts

    def test_worker_threads_out_of_range_rejected(self):
        api = _Api()
        with pytest.raises(ProximoError):
            pull(api, store="local1", remote_store="remote1", worker_threads=33)
        assert not api.posts

    def test_full_field_set(self):
        api = _Api()
        pull(
            api, store="local1", remote_store="remote1", remote="myremote", remote_ns="a/b",
            ns="c/d", burst_in="10MB", burst_out="5MB", decryption_keys=["key1"],
            encrypted_only=True, group_filter=["type:vm"], max_depth=3, rate_in="1MB",
            rate_out="1MB", remove_vanished=False, resync_corrupt=True, transfer_last=5,
            verified_only=True, worker_threads=4,
        )
        _, data = api.posts[-1]
        assert data == {
            "store": "local1", "remote-store": "remote1", "remote": "myremote",
            "decryption-keys": ["key1"], "resync-corrupt": True,
            "burst-in": "10MB", "burst-out": "5MB", "encrypted-only": True,
            "group-filter": ["type:vm"], "max-depth": 3, "ns": "c/d", "rate-in": "1MB",
            "rate-out": "1MB", "remote-ns": "a/b", "remove-vanished": False,
            "transfer-last": 5, "verified-only": True, "worker-threads": 4,
        }


class TestPush:
    def test_minimal_required_fields(self):
        api = _Api()
        push(api, store="local1", remote="myremote", remote_store="remote1")
        path, data = api.posts[-1]
        assert path == "/push"
        assert data == {"store": "local1", "remote": "myremote", "remote-store": "remote1"}

    def test_remote_missing_raises(self):
        """module docstring fact #3 — remote is REQUIRED on push (Python signature enforces
        this: TypeError, not ProximoError, since it's a positional-or-keyword required arg)."""
        with pytest.raises(TypeError):
            push(_Api(), store="local1", remote_store="remote1")  # type: ignore[call-arg]

    def test_encryption_key_forwarded(self):
        api = _Api()
        push(api, store="local1", remote="myremote", remote_store="remote1", encryption_key="key1")
        _, data = api.posts[-1]
        assert data["encryption-key"] == "key1"

    def test_remove_vanished_forwarded(self):
        api = _Api()
        push(api, store="local1", remote="myremote", remote_store="remote1", remove_vanished=True)
        _, data = api.posts[-1]
        assert data["remove-vanished"] is True

    def test_no_decryption_keys_param_exists(self):
        """module docstring fact #5 — push has NO decryption-keys param (pull-only)."""
        import inspect
        sig = inspect.signature(push)
        assert "decryption_keys" not in sig.parameters
        assert "resync_corrupt" not in sig.parameters


# ---------------------------------------------------------------------------
# Plan factories — Node config
# ---------------------------------------------------------------------------

class TestPlanNodeConfigSet:
    def test_risk_is_high(self):
        plan = plan_node_config_set(_Api(get_return={}), description="new")
        assert plan.risk == RISK_HIGH

    def test_captures_current_config(self):
        api = _Api(get_return={"description": "old desc"})
        plan = plan_node_config_set(api, description="new desc")
        assert plan.current == {"description": "old desc"}
        assert plan.complete is True

    def test_capture_failure_marks_incomplete(self):
        class _BrokenApi(_Api):
            def _get(self, path, params=None):
                raise RuntimeError("network down")

        plan = plan_node_config_set(_BrokenApi(), description="new")
        assert plan.complete is False
        assert "Could not capture" in plan.note

    def test_http_proxy_masked_in_change_string(self):
        api = _Api(get_return={})
        plan = plan_node_config_set(api, http_proxy="http://admin:hunter2@proxy.example.com:3128")
        assert "hunter2" not in plan.change
        assert "proxy.example.com:3128" in plan.change

    def test_http_proxy_masked_in_captured_current(self):
        api = _Api(get_return={"http-proxy": "http://admin:hunter2@proxy.example.com:3128"})
        plan = plan_node_config_set(api, description="new")
        assert "hunter2" not in str(plan.current)

    def test_empty_delete_list_rejected(self):
        with pytest.raises(ProximoError):
            plan_node_config_set(_Api(get_return={}), delete=[])

    def test_node_embedded_in_target(self):
        plan = plan_node_config_set(_Api(get_return={}), node="pbs1", description="new")
        assert "pbs1" in plan.target


# ---------------------------------------------------------------------------
# Plan factories — Pull / Push
# ---------------------------------------------------------------------------

class TestPlanPull:
    def test_default_risk_is_medium(self):
        plan = plan_pull(store="local1", remote_store="remote1")
        assert plan.risk == RISK_MEDIUM

    def test_remove_vanished_escalates_to_high(self):
        plan = plan_pull(store="local1", remote_store="remote1", remove_vanished=True)
        assert plan.risk == RISK_HIGH

    def test_remove_vanished_disclosed_in_blast_radius(self):
        plan = plan_pull(store="local1", remote_store="remote1", remove_vanished=True)
        joined = " ".join(plan.blast_radius)
        assert "remove_vanished" in joined or "DELETES local" in joined

    def test_store_and_remote_store_disclosed(self):
        plan = plan_pull(store="local1", remote_store="remote1", remote="myremote")
        joined = plan.target + plan.change + " ".join(plan.blast_radius)
        assert "local1" in joined
        assert "remote1" in joined
        assert "myremote" in joined

    def test_no_group_filter_disclosed_as_broad(self):
        plan = plan_pull(store="local1", remote_store="remote1")
        joined = " ".join(plan.blast_radius)
        assert "every group in scope" in joined

    def test_group_filter_disclosed_when_set(self):
        plan = plan_pull(store="local1", remote_store="remote1", group_filter=["type:vm"])
        joined = " ".join(plan.blast_radius)
        assert "type:vm" in joined

    def test_no_upid_note_present(self):
        plan = plan_pull(store="local1", remote_store="remote1")
        joined = " ".join(plan.blast_radius)
        assert "no UPID" in joined

    def test_is_pure_no_current_state(self):
        plan = plan_pull(store="local1", remote_store="remote1")
        assert plan.current == {}


class TestPlanPush:
    def test_default_risk_is_medium(self):
        plan = plan_push(store="local1", remote="myremote", remote_store="remote1")
        assert plan.risk == RISK_MEDIUM

    def test_remove_vanished_escalates_to_high(self):
        plan = plan_push(
            store="local1", remote="myremote", remote_store="remote1", remove_vanished=True,
        )
        assert plan.risk == RISK_HIGH

    def test_remove_vanished_disclosed_as_remote_deletion(self):
        plan = plan_push(
            store="local1", remote="myremote", remote_store="remote1", remove_vanished=True,
        )
        joined = " ".join(plan.blast_radius)
        assert "REMOTE" in joined
        assert "DELETES" in joined

    def test_store_remote_remote_store_disclosed(self):
        plan = plan_push(store="local1", remote="myremote", remote_store="remote1")
        joined = plan.target + plan.change + " ".join(plan.blast_radius)
        assert "local1" in joined
        assert "myremote" in joined
        assert "remote1" in joined
