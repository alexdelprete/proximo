"""TDD tests for the PBS S3 client configs + client encryption keys plane (Wave 5a, full-surface
campaign) — fully mocked, no live PBS.

Mirrors test_pbs_tape_media.py's style: a recording fake PBS API, validator rejection tests
(\\Z-anchored), backend-function path/verb/payload tests, and plan-factory risk/blast-radius
tests. Adds the SECRET CONTRACT tests (module docstring fact #1/#8): `secret-key`/`key` must
never appear in a Plan's `change`/`current` string, while `access-key` (deliberately NOT
redacted) always does when supplied.

Covers: validators (id, endpoint, region, fingerprint, digest, bucket, store_prefix, byte_size,
port, provider_quirks, key_material); backend functions for all 12 ops (4 read, 8 mutation); plan
factories (RISK_MEDIUM s3 client create/update/delete + encryption key create/toggle_archive,
RISK_LOW s3 check/reset_counters, RISK_HIGH encryption key delete); the secret-redaction
contract; module structure.
"""

from __future__ import annotations

import pytest

from proximo.backends import ProximoError
from proximo.pbs_s3 import (
    _check_bucket,
    _check_byte_size,
    _check_digest,
    _check_endpoint,
    _check_fingerprint,
    _check_id,
    _check_key_material,
    _check_port,
    _check_provider_quirks,
    _check_region,
    _check_store_prefix,
    _redact_secrets,
    encryption_key_create,
    encryption_key_delete,
    encryption_key_list,
    encryption_key_toggle_archive,
    plan_encryption_key_create,
    plan_encryption_key_delete,
    plan_encryption_key_toggle_archive,
    plan_s3_check,
    plan_s3_client_create,
    plan_s3_client_delete,
    plan_s3_client_update,
    plan_s3_reset_counters,
    s3_check,
    s3_client_create,
    s3_client_delete,
    s3_client_get,
    s3_client_list,
    s3_client_update,
    s3_list_buckets,
    s3_reset_counters,
)
from proximo.planning import RISK_HIGH, RISK_LOW, RISK_MEDIUM

_FP = ":".join(["ab"] * 32)  # a well-formed 32-colon-separated-hex-byte-pair fingerprint


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
    import proximo.pbs_s3 as m
    doc = m.__doc__ or ""
    assert "secret-key" in doc.lower()
    assert "access-key" in doc.lower()
    assert "fingerprint" in doc.lower()


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

class TestCheckId:
    def test_valid_simple(self):
        assert _check_id("myendpoint1") == "myendpoint1"

    def test_valid_with_dot_underscore_hyphen(self):
        assert _check_id("s3-endpoint.a_1") == "s3-endpoint.a_1"

    def test_min_length_three_enforced(self):
        with pytest.raises(ProximoError):
            _check_id("ab")

    def test_min_length_three_accepted(self):
        assert _check_id("abc") == "abc"

    def test_max_length_32_enforced(self):
        with pytest.raises(ProximoError):
            _check_id("a" * 33)

    def test_max_length_32_accepted(self):
        assert _check_id("a" * 32) == "a" * 32

    def test_slash_raises(self):
        with pytest.raises(ProximoError):
            _check_id("name/slash")

    def test_trailing_newline_raises(self):
        with pytest.raises(ProximoError):
            _check_id("myendpoint\n")

    def test_empty_raises(self):
        with pytest.raises(ProximoError):
            _check_id("")

    def test_leading_dot_rejected(self):
        with pytest.raises(ProximoError):
            _check_id(".myendpoint")


class TestCheckEndpoint:
    def test_hostname_accepted(self):
        assert _check_endpoint("s3.amazonaws.com") == "s3.amazonaws.com"

    def test_ipv4_accepted(self):
        assert _check_endpoint("192.168.1.1") == "192.168.1.1"

    def test_ipv6_accepted(self):
        assert _check_endpoint("2001:db8::1") == "2001:db8::1"

    def test_templated_endpoint_accepted(self):
        assert _check_endpoint("{{bucket}}.s3.{{region}}.example.com") == "{{bucket}}.s3.{{region}}.example.com"

    def test_localhost_accepted(self):
        assert _check_endpoint("localhost") == "localhost"

    def test_trailing_newline_rejected(self):
        with pytest.raises(ProximoError):
            _check_endpoint("s3.amazonaws.com\n")

    def test_space_rejected(self):
        with pytest.raises(ProximoError):
            _check_endpoint("s3 amazonaws com")


class TestCheckRegion:
    def test_valid(self):
        assert _check_region("us-east-1") == "us-east-1"

    def test_single_char_rejected(self):
        with pytest.raises(ProximoError):
            _check_region("a")

    def test_uppercase_rejected(self):
        with pytest.raises(ProximoError):
            _check_region("US-EAST-1")

    def test_over_32_rejected(self):
        with pytest.raises(ProximoError):
            _check_region("a" * 33)

    def test_trailing_newline_rejected(self):
        with pytest.raises(ProximoError):
            _check_region("us-east-1\n")


class TestCheckFingerprint:
    def test_valid(self):
        assert _check_fingerprint(_FP) == _FP

    def test_too_few_pairs_rejected(self):
        with pytest.raises(ProximoError):
            _check_fingerprint("AA:BB:CC:DD:EE:FF")

    def test_non_hex_rejected(self):
        with pytest.raises(ProximoError):
            _check_fingerprint(":".join(["zz"] * 32))


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


class TestCheckBucket:
    def test_valid(self):
        assert _check_bucket("my-bucket") == "my-bucket"

    def test_min_length_three_enforced(self):
        with pytest.raises(ProximoError):
            _check_bucket("ab")

    def test_max_length_63_enforced(self):
        with pytest.raises(ProximoError):
            _check_bucket("a" * 64)

    def test_control_char_rejected(self):
        with pytest.raises(ProximoError):
            _check_bucket("buc\x00ket")


class TestCheckStorePrefix:
    def test_valid(self):
        assert _check_store_prefix("mydatastore") == "mydatastore"

    def test_empty_allowed(self):
        assert _check_store_prefix("") == ""

    def test_over_256_rejected(self):
        with pytest.raises(ProximoError):
            _check_store_prefix("a" * 257)

    def test_control_char_rejected(self):
        with pytest.raises(ProximoError):
            _check_store_prefix("a\x01b")


class TestCheckByteSize:
    def test_valid(self):
        assert _check_byte_size("10MB", "rate_in") == "10MB"

    def test_empty_rejected(self):
        with pytest.raises(ProximoError):
            _check_byte_size("", "rate_in")

    def test_over_64_rejected(self):
        with pytest.raises(ProximoError):
            _check_byte_size("a" * 65, "rate_in")

    def test_control_char_rejected(self):
        with pytest.raises(ProximoError):
            _check_byte_size("10\x00MB", "rate_in")


class TestCheckPort:
    def test_valid(self):
        assert _check_port(443) == 443

    def test_zero_rejected(self):
        with pytest.raises(ProximoError):
            _check_port(0)

    def test_over_65535_rejected(self):
        with pytest.raises(ProximoError):
            _check_port(65536)

    def test_non_integer_rejected(self):
        with pytest.raises(ProximoError):
            _check_port("not-a-port")


class TestCheckProviderQuirks:
    def test_valid(self):
        assert _check_provider_quirks(["skip-if-none-match-header"]) == ["skip-if-none-match-header"]

    def test_both_valid(self):
        out = _check_provider_quirks(["skip-if-none-match-header", "delete-objects-via-delete-object"])
        assert out == ["skip-if-none-match-header", "delete-objects-via-delete-object"]

    def test_invalid_rejected(self):
        with pytest.raises(ProximoError):
            _check_provider_quirks(["not-a-real-quirk"])

    def test_empty_list_accepted(self):
        assert _check_provider_quirks([]) == []


class TestCheckKeyMaterial:
    def test_valid(self):
        assert _check_key_material("some-key-blob-content") == "some-key-blob-content"

    def test_empty_rejected(self):
        with pytest.raises(ProximoError):
            _check_key_material("")

    def test_control_char_rejected(self):
        with pytest.raises(ProximoError):
            _check_key_material("key\x00blob")

    def test_no_length_bound_unlike_tape(self):
        """Module docstring fact #8: NO length bound on this plane's key material, unlike tape's
        300-600 char requirement — a very long blob is still accepted."""
        assert _check_key_material("k" * 1000) == "k" * 1000


class TestRedactSecrets:
    def test_secret_key_redacted(self):
        out = _redact_secrets({"secret-key": "sekrit", "access-key": "pub"})
        assert out["secret-key"] == "[redacted]"

    def test_key_redacted(self):
        out = _redact_secrets({"key": "sekrit-blob"})
        assert out["key"] == "[redacted]"

    def test_access_key_never_redacted(self):
        """Module docstring fact #1's decision: access-key is deliberately NOT in _SECRET_KEYS."""
        out = _redact_secrets({"access-key": "AKIA-sentinel-not-secret"})
        assert out["access-key"] == "AKIA-sentinel-not-secret"

    def test_non_secret_untouched(self):
        out = _redact_secrets({"region": "us-east-1", "port": 443})
        assert out["region"] == "us-east-1"
        assert out["port"] == 443


# ---------------------------------------------------------------------------
# Backend functions — reads, S3 client configs
# ---------------------------------------------------------------------------

class TestS3ClientList:
    def test_calls_correct_path(self):
        api = _Api(get_return=[{"id": "s3a", "access-key": "AKIA1"}])
        result = s3_client_list(api)
        assert api.gets == [("/config/s3", None)]
        assert result[0]["access-key"] == "AKIA1"

    def test_empty_api_returns_empty_list(self):
        api = _Api(get_return=None)
        assert s3_client_list(api) == []

    def test_secret_key_stripped_defensively(self):
        """Review finding (Wave 5a): PBS documents reads as secret-free, but never trust it
        blindly — mirror pbs_config.remote_get's defensive strip."""
        api = _Api(get_return=[{"id": "s3a", "secret-key": "sentinel-leaked-secret"}])
        result = s3_client_list(api)
        assert "secret-key" not in result[0]


class TestS3ClientGet:
    def test_correct_path(self):
        api = _Api(get_return={"id": "s3a"})
        result = s3_client_get(api, "s3a")
        assert api.gets == [("/config/s3/s3a", None)]
        assert result["id"] == "s3a"

    def test_secret_key_stripped_defensively(self):
        api = _Api(get_return={"id": "s3a", "secret-key": "sentinel-leaked-secret"})
        result = s3_client_get(api, "s3a")
        assert "secret-key" not in result

    def test_invalid_id_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            s3_client_get(api, "ab")


class TestS3ListBuckets:
    def test_correct_path(self):
        api = _Api(get_return=["bucket1", "bucket2"])
        result = s3_list_buckets(api, "s3a")
        assert api.gets == [("/config/s3/s3a/list-buckets", None)]
        assert result == ["bucket1", "bucket2"]

    def test_none_returns_empty_list(self):
        api = _Api(get_return=None)
        assert s3_list_buckets(api, "s3a") == []


# ---------------------------------------------------------------------------
# Backend functions — mutations, S3 client configs
# ---------------------------------------------------------------------------

class TestS3ClientCreate:
    def test_posts_minimal_required_fields(self):
        api = _Api()
        s3_client_create(api, "s3a", "s3.example.com", "AKIA1", "sentinel-secret-value")
        assert len(api.posts) == 1
        path, data = api.posts[0]
        assert path == "/config/s3"
        assert data == {
            "id": "s3a", "endpoint": "s3.example.com",
            "access-key": "AKIA1", "secret-key": "sentinel-secret-value",
        }

    def test_all_optional_fields_forwarded(self):
        api = _Api()
        s3_client_create(
            api, "s3a", "s3.example.com", "AKIA1", "sentinel-secret-value",
            region="us-east-1", fingerprint=_FP, port=443, path_style=True,
            provider_quirks=["skip-if-none-match-header"], rate_in="10MB", rate_out="20MB",
            burst_in="30MB", burst_out="40MB",
        )
        _, data = api.posts[0]
        assert data["region"] == "us-east-1"
        assert data["fingerprint"] == _FP
        assert data["port"] == 443
        assert data["path-style"] is True
        assert data["provider-quirks"] == ["skip-if-none-match-header"]
        assert data["rate-in"] == "10MB"
        assert data["burst-out"] == "40MB"

    def test_invalid_id_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            s3_client_create(api, "ab", "s3.example.com", "AKIA1", "sentinel-secret-value")

    def test_invalid_endpoint_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            s3_client_create(api, "s3a", "bad endpoint with spaces", "AKIA1", "sentinel-secret-value")

    def test_no_put_rate_limit_param_exists(self):
        """Module docstring fact #2: put-rate-limit is NOT settable via create — the function
        signature doesn't even accept one."""
        import inspect
        sig = inspect.signature(s3_client_create)
        assert "put_rate_limit" not in sig.parameters


class TestS3ClientUpdate:
    def test_puts_to_correct_path(self):
        api = _Api()
        s3_client_update(api, "s3a", region="us-west-2")
        assert len(api.puts) == 1
        path, data = api.puts[0]
        assert path == "/config/s3/s3a"
        assert data == {"region": "us-west-2"}

    def test_none_kwargs_excluded(self):
        api = _Api()
        s3_client_update(api, "s3a")
        _, data = api.puts[0]
        assert data == {}

    def test_digest_forwarded(self):
        api = _Api()
        s3_client_update(api, "s3a", digest="a" * 64)
        _, data = api.puts[0]
        assert data["digest"] == "a" * 64

    def test_delete_list_forwarded(self):
        api = _Api()
        s3_client_update(api, "s3a", delete=["region", "port"])
        _, data = api.puts[0]
        assert data["delete"] == ["region", "port"]

    def test_secret_key_rotation_forwarded(self):
        api = _Api()
        s3_client_update(api, "s3a", secret_key="sentinel-new-secret")
        _, data = api.puts[0]
        assert data["secret-key"] == "sentinel-new-secret"

    def test_invalid_id_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            s3_client_update(api, "ab")


class TestS3ClientDelete:
    def test_deletes_correct_path(self):
        api = _Api()
        s3_client_delete(api, "s3a")
        assert api.dels[0][0] == "/config/s3/s3a"
        assert api.dels[0][1] == {}

    def test_digest_forwarded(self):
        api = _Api()
        s3_client_delete(api, "s3a", digest="c" * 64)
        assert api.dels[0][1] == {"digest": "c" * 64}

    def test_invalid_id_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            s3_client_delete(api, "ab")


class TestS3Check:
    def test_puts_to_correct_path(self):
        api = _Api()
        s3_check(api, "s3a", "my-bucket")
        assert len(api.puts) == 1
        path, data = api.puts[0]
        assert path == "/admin/s3/s3a/check"
        assert data == {"bucket": "my-bucket"}

    def test_store_prefix_forwarded(self):
        api = _Api()
        s3_check(api, "s3a", "my-bucket", store_prefix="myds")
        _, data = api.puts[0]
        assert data == {"bucket": "my-bucket", "store-prefix": "myds"}

    def test_no_digest_param_exists(self):
        import inspect
        sig = inspect.signature(s3_check)
        assert "digest" not in sig.parameters

    def test_invalid_bucket_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            s3_check(api, "s3a", "ab")


class TestS3ResetCounters:
    def test_puts_to_correct_path(self):
        api = _Api()
        s3_reset_counters(api, "s3a", "my-bucket")
        assert len(api.puts) == 1
        path, data = api.puts[0]
        assert path == "/admin/s3/s3a/reset-counters"
        assert data == {"bucket": "my-bucket"}

    def test_invalid_id_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            s3_reset_counters(api, "ab", "my-bucket")


# ---------------------------------------------------------------------------
# Backend functions — Client encryption keys
# ---------------------------------------------------------------------------

class TestEncryptionKeyList:
    def test_default_excludes_archived(self):
        api = _Api(get_return=[{"id": "key1"}])
        result = encryption_key_list(api)
        assert api.gets == [("/config/encryption-keys", {"include-archived": False})]
        assert result[0]["id"] == "key1"

    def test_include_archived_forwarded(self):
        api = _Api(get_return=[])
        encryption_key_list(api, include_archived=True)
        assert api.gets == [("/config/encryption-keys", {"include-archived": True})]

    def test_empty_api_returns_empty_list(self):
        api = _Api(get_return=None)
        assert encryption_key_list(api) == []


class TestEncryptionKeyCreate:
    def test_posts_id_only(self):
        api = _Api()
        encryption_key_create(api, "key1")
        assert len(api.posts) == 1
        path, data = api.posts[0]
        assert path == "/config/encryption-keys"
        assert data == {"id": "key1"}

    def test_key_material_forwarded(self):
        api = _Api()
        encryption_key_create(api, "key1", key="sentinel-key-blob")
        _, data = api.posts[0]
        assert data == {"id": "key1", "key": "sentinel-key-blob"}

    def test_no_password_param_exists(self):
        """Module docstring fact #8: NO password/hint/kdf param exists on this endpoint at all —
        a real divergence from the tape-encryption-keys plane."""
        import inspect
        sig = inspect.signature(encryption_key_create)
        assert "password" not in sig.parameters
        assert "hint" not in sig.parameters
        assert "kdf" not in sig.parameters

    def test_invalid_id_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            encryption_key_create(api, "ab")

    def test_invalid_key_material_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            encryption_key_create(api, "key1", key="")


class TestEncryptionKeyDelete:
    def test_deletes_correct_path(self):
        api = _Api()
        encryption_key_delete(api, "key1")
        assert api.dels[0][0] == "/config/encryption-keys/key1"
        assert api.dels[0][1] == {}

    def test_digest_forwarded(self):
        api = _Api()
        encryption_key_delete(api, "key1", digest="d" * 64)
        assert api.dels[0][1] == {"digest": "d" * 64}

    def test_invalid_id_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            encryption_key_delete(api, "ab")


class TestEncryptionKeyToggleArchive:
    def test_posts_to_correct_path(self):
        api = _Api()
        encryption_key_toggle_archive(api, "key1")
        assert len(api.posts) == 1
        path, data = api.posts[0]
        assert path == "/config/encryption-keys/key1"
        assert data == {}

    def test_digest_forwarded(self):
        api = _Api()
        encryption_key_toggle_archive(api, "key1", digest="e" * 64)
        _, data = api.posts[0]
        assert data == {"digest": "e" * 64}

    def test_invalid_id_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            encryption_key_toggle_archive(api, "ab")


# ---------------------------------------------------------------------------
# Plan factories — S3 client configs
# ---------------------------------------------------------------------------

class TestPlanS3ClientCreate:
    def test_is_medium_risk(self):
        """Module docstring's RISK RATING note: MEDIUM (mirrors pbs_remote_create), NOT the LOW
        rating a naive additive-config reading might suggest."""
        plan = plan_s3_client_create("s3a", "s3.example.com", "AKIA1", "sentinel-secret-value")
        assert plan.risk == RISK_MEDIUM

    def test_target_correct(self):
        plan = plan_s3_client_create("s3a", "s3.example.com", "AKIA1", "sentinel-secret-value")
        assert plan.target == "pbs/config/s3/s3a"

    def test_current_is_empty(self):
        plan = plan_s3_client_create("s3a", "s3.example.com", "AKIA1", "sentinel-secret-value")
        assert plan.current == {}

    def test_secret_key_never_in_change(self):
        plan = plan_s3_client_create("s3a", "s3.example.com", "AKIA1", "sentinel-secret-value")
        assert "sentinel-secret-value" not in plan.change

    def test_access_key_shown_unredacted(self):
        """Module docstring fact #1's decision: access-key is NOT redacted."""
        plan = plan_s3_client_create("s3a", "s3.example.com", "AKIA-sentinel-visible", "sentinel-secret-value")
        assert "AKIA-sentinel-visible" in plan.change

    def test_invalid_id_raises(self):
        with pytest.raises(ProximoError):
            plan_s3_client_create("ab", "s3.example.com", "AKIA1", "sentinel-secret-value")

    def test_invalid_endpoint_raises(self):
        with pytest.raises(ProximoError):
            plan_s3_client_create("s3a", "bad endpoint", "AKIA1", "sentinel-secret-value")


class TestPlanS3ClientUpdate:
    def test_reads_current_from_api(self):
        api = _Api(get_return={"id": "s3a", "region": "us-east-1"})
        plan = plan_s3_client_update(api, "s3a", region="us-west-2")
        assert plan.risk == RISK_MEDIUM
        assert plan.current == {"id": "s3a", "region": "us-east-1"}

    def test_no_fields_changed_message(self):
        api = _Api(get_return={"id": "s3a"})
        plan = plan_s3_client_update(api, "s3a")
        assert "no fields changed" in plan.change

    def test_secret_key_never_in_change(self):
        api = _Api(get_return={"id": "s3a"})
        plan = plan_s3_client_update(api, "s3a", secret_key="sentinel-new-secret")
        assert "sentinel-new-secret" not in plan.change

    def test_access_key_shown_unredacted(self):
        api = _Api(get_return={"id": "s3a"})
        plan = plan_s3_client_update(api, "s3a", access_key="AKIA-sentinel-visible")
        assert "AKIA-sentinel-visible" in plan.change

    def test_empty_delete_list_rejected(self):
        # Wave 5b review finding 1 (traced against this exact site): delete=[] used to be
        # DISCLOSED in the plan on the theory that it's "a real wire payload the execute side
        # sends" — false. httpx's form encoding drops an empty-list value entirely, so it never
        # reaches the wire. Reject loudly instead of disclosing a payload confirm=True never sends.
        api = _Api(get_return={"id": "s3a"})
        with pytest.raises(ProximoError):
            plan_s3_client_update(api, "s3a", delete=[])

    def test_captured_current_defensively_redacted_even_when_secret_bearing(self):
        api = _Api(get_return={"id": "s3a", "secret-key": "sentinel-leaked-secret"})
        plan = plan_s3_client_update(api, "s3a", region="us-west-2")
        assert "secret-key" not in plan.current  # stripped at the read layer — stronger than redaction
        assert "sentinel-leaked-secret" not in str(plan.current)

    def test_invalid_id_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            plan_s3_client_update(api, "ab")


class TestPlanS3ClientDelete:
    def test_is_medium_risk(self):
        api = _Api(get_return={"id": "s3a"})
        plan = plan_s3_client_delete(api, "s3a")
        assert plan.risk == RISK_MEDIUM

    def test_reads_current_from_api(self):
        api = _Api(get_return={"id": "s3a", "region": "us-east-1"})
        plan = plan_s3_client_delete(api, "s3a")
        assert plan.current == {"id": "s3a", "region": "us-east-1"}

    def test_captured_current_defensively_redacted(self):
        api = _Api(get_return={"id": "s3a", "secret-key": "sentinel-leaked-secret"})
        plan = plan_s3_client_delete(api, "s3a")
        assert "secret-key" not in plan.current  # stripped at the read layer — stronger than redaction

    def test_cannot_be_retrieved_language(self):
        api = _Api(get_return={"id": "s3a"})
        plan = plan_s3_client_delete(api, "s3a")
        haystack = " ".join(plan.blast_radius).lower()
        assert "cannot be retrieved" in haystack

    def test_invalid_id_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            plan_s3_client_delete(api, "ab")


class TestPlanS3Check:
    def test_is_low_risk(self):
        plan = plan_s3_check("s3a", "my-bucket")
        assert plan.risk == RISK_LOW

    def test_target_correct(self):
        plan = plan_s3_check("s3a", "my-bucket")
        assert plan.target == "pbs/admin/s3/s3a/check/my-bucket"

    def test_current_is_empty(self):
        plan = plan_s3_check("s3a", "my-bucket")
        assert plan.current == {}

    def test_no_undo_needed_note(self):
        plan = plan_s3_check("s3a", "my-bucket")
        assert "no undo needed" in plan.note.lower()

    def test_invalid_bucket_raises(self):
        with pytest.raises(ProximoError):
            plan_s3_check("s3a", "ab")


class TestPlanS3ResetCounters:
    def test_is_low_risk(self):
        plan = plan_s3_reset_counters("s3a", "my-bucket")
        assert plan.risk == RISK_LOW

    def test_observability_language_present(self):
        plan = plan_s3_reset_counters("s3a", "my-bucket")
        haystack = " ".join(plan.blast_radius).lower()
        assert "observability" in haystack
        assert "not data" in haystack or "not" in haystack

    def test_invalid_bucket_raises(self):
        with pytest.raises(ProximoError):
            plan_s3_reset_counters("s3a", "ab")


# ---------------------------------------------------------------------------
# Plan factories — Client encryption keys
# ---------------------------------------------------------------------------

class TestPlanEncryptionKeyCreate:
    def test_is_medium_risk(self):
        plan = plan_encryption_key_create("key1")
        assert plan.risk == RISK_MEDIUM

    def test_target_correct(self):
        plan = plan_encryption_key_create("key1")
        assert plan.target == "pbs/config/encryption-keys/key1"

    def test_key_material_never_in_change(self):
        key_material = "sentinel-key-material-" + "k" * 280
        plan = plan_encryption_key_create("key1", key=key_material)
        assert key_material not in plan.change

    def test_current_is_empty(self):
        plan = plan_encryption_key_create("key1")
        assert plan.current == {}

    def test_invalid_id_raises(self):
        with pytest.raises(ProximoError):
            plan_encryption_key_create("ab")

    def test_invalid_key_material_raises(self):
        with pytest.raises(ProximoError):
            plan_encryption_key_create("key1", key="")


class TestPlanEncryptionKeyDelete:
    def test_is_high_risk(self):
        plan = plan_encryption_key_delete("key1")
        assert plan.risk == RISK_HIGH

    def test_no_undo_language(self):
        plan = plan_encryption_key_delete("key1")
        assert "no undo" in plan.note.lower()

    def test_inferred_not_schema_stated_language(self):
        """Module docstring fact #11: PBS's own DELETE description is bare — this module never
        claims schema-verified consequence language the way the tape plane's does."""
        plan = plan_encryption_key_delete("key1")
        haystack = " ".join(plan.blast_radius).lower()
        assert "inferred" in haystack or "not schema-verified" in haystack or "not state" in haystack

    def test_invalid_id_raises(self):
        with pytest.raises(ProximoError):
            plan_encryption_key_delete("ab")

    def test_invalid_digest_raises(self):
        with pytest.raises(ProximoError):
            plan_encryption_key_delete("key1", digest="not-hex")


class TestPlanEncryptionKeyToggleArchive:
    def test_is_medium_risk(self):
        plan = plan_encryption_key_toggle_archive("key1")
        assert plan.risk == RISK_MEDIUM

    def test_reversible_note(self):
        plan = plan_encryption_key_toggle_archive("key1")
        assert "reversible" in plan.note.lower()

    def test_invalid_id_raises(self):
        with pytest.raises(ProximoError):
            plan_encryption_key_toggle_archive("ab")
