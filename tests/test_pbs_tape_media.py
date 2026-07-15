"""TDD tests for the PBS tape media-pool + encryption-key config plane (Wave 4b, full-surface
campaign) — fully mocked, no live PBS.

Mirrors test_pbs_tape_config.py's style: a recording fake PBS API, validator rejection tests
(\\Z-anchored), backend-function path/verb/payload tests, and plan-factory risk/blast-radius
tests. Adds the SECRET CONTRACT tests (module docstring fact #7): `key`/`password`/
`new-password` must never appear in a Plan's `change`/`current` string.

Covers: validators (pool name, fingerprint, digest, kdf, policy string, no-control); backend
functions for all 10 ops (4 read, 6 mutation); plan factories (RISK_LOW pool create, RISK_MEDIUM
pool update/delete + key create/update, RISK_HIGH key delete — see module docstring's RISK
RATING section); the secret-redaction contract; module structure.
"""

from __future__ import annotations

import pytest

from proximo.backends import ProximoError
from proximo.pbs_tape_media import (
    _check_digest,
    _check_fingerprint,
    _check_kdf,
    _check_no_control,
    _check_policy_string,
    _check_pool_name,
    _redact_secrets,
    plan_tape_key_create,
    plan_tape_key_delete,
    plan_tape_key_update_password,
    plan_tape_pool_create,
    plan_tape_pool_delete,
    plan_tape_pool_update,
    tape_key_create,
    tape_key_delete,
    tape_key_get,
    tape_key_list,
    tape_key_update_password,
    tape_pool_create,
    tape_pool_delete,
    tape_pool_get,
    tape_pool_list,
    tape_pool_update,
)
from proximo.planning import RISK_HIGH, RISK_LOW, RISK_MEDIUM

_FP = ":".join(["ab"] * 32)  # a well-formed 32-colon-separated-hex-byte-pair fingerprint
_FP2 = ":".join(["cd"] * 32)

# ---------------------------------------------------------------------------
# Recording fake
# ---------------------------------------------------------------------------

class _Api:
    """Recording fake for PbsBackend (HTTP verb tracking, no live network)."""

    def __init__(self, get_return=None):
        self._get_return = get_return
        self.gets: list[str] = []
        self.posts: list[tuple] = []
        self.puts: list[tuple] = []
        self.dels: list[tuple] = []

    def _get(self, path: str, params=None):
        self.gets.append(path)
        return self._get_return

    def _post(self, path: str, data=None):
        self.posts.append((path, data))
        return self._get_return if isinstance(self._get_return, str) else None

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
    import proximo.pbs_tape_media as m
    doc = m.__doc__ or ""
    assert "fingerprint" in doc.lower()
    assert "password" in doc.lower()
    assert "key" in doc.lower()


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

class TestCheckPoolName:
    def test_valid_simple(self):
        assert _check_pool_name("pool1") == "pool1"

    def test_valid_with_dot_underscore_hyphen(self):
        assert _check_pool_name("lto-9.a_1") == "lto-9.a_1"

    def test_min_length_two_enforced(self):
        with pytest.raises(ProximoError):
            _check_pool_name("a")

    def test_min_length_two_accepted(self):
        assert _check_pool_name("ab") == "ab"

    def test_max_length_32_enforced(self):
        with pytest.raises(ProximoError):
            _check_pool_name("a" * 33)

    def test_max_length_32_accepted(self):
        assert _check_pool_name("a" * 32) == "a" * 32

    def test_slash_raises(self):
        with pytest.raises(ProximoError):
            _check_pool_name("name/slash")

    def test_trailing_newline_raises(self):
        with pytest.raises(ProximoError):
            _check_pool_name("pool1\n")

    def test_empty_raises(self):
        with pytest.raises(ProximoError):
            _check_pool_name("")

    def test_control_char_raises(self):
        with pytest.raises(ProximoError):
            _check_pool_name("po\x00ol1")

    def test_leading_dot_rejected(self):
        with pytest.raises(ProximoError):
            _check_pool_name(".pool1")


class TestCheckFingerprint:
    def test_valid(self):
        assert _check_fingerprint(_FP) == _FP

    def test_uppercase_accepted(self):
        fp = ":".join(["AB"] * 32)
        assert _check_fingerprint(fp) == fp

    def test_too_few_pairs_rejected(self):
        with pytest.raises(ProximoError):
            _check_fingerprint("AA:BB:CC:DD:EE:FF")

    def test_too_many_pairs_rejected(self):
        with pytest.raises(ProximoError):
            _check_fingerprint(":".join(["ab"] * 33))

    def test_no_colons_rejected(self):
        with pytest.raises(ProximoError):
            _check_fingerprint("ab" * 32)

    def test_trailing_newline_rejected(self):
        with pytest.raises(ProximoError):
            _check_fingerprint(_FP + "\n")

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

    def test_trailing_newline_rejected(self):
        with pytest.raises(ProximoError):
            _check_digest("a" * 64 + "\n")


class TestCheckKdf:
    @pytest.mark.parametrize("kdf", ["none", "scrypt", "pbkdf2"])
    def test_valid_values(self, kdf):
        assert _check_kdf(kdf) == kdf

    def test_invalid_value_rejected(self):
        with pytest.raises(ProximoError):
            _check_kdf("md5")

    def test_empty_rejected(self):
        with pytest.raises(ProximoError):
            _check_kdf("")


class TestCheckNoControl:
    def test_valid(self):
        assert _check_no_control("hello world", "field") == "hello world"

    def test_empty_allowed_by_default(self):
        assert _check_no_control("", "field") == ""

    def test_control_char_rejected(self):
        with pytest.raises(ProximoError):
            _check_no_control("a\x00b", "field")

    def test_newline_rejected(self):
        with pytest.raises(ProximoError):
            _check_no_control("a\nb", "field")

    def test_min_len_enforced(self):
        with pytest.raises(ProximoError):
            _check_no_control("", "field", min_len=1)

    def test_max_len_enforced(self):
        with pytest.raises(ProximoError):
            _check_no_control("a" * 65, "field", max_len=64)


class TestCheckPolicyString:
    def test_valid(self):
        assert _check_policy_string("always", "allocation") == "always"

    def test_empty_rejected(self):
        with pytest.raises(ProximoError):
            _check_policy_string("", "allocation")

    def test_over_256_rejected(self):
        with pytest.raises(ProximoError):
            _check_policy_string("a" * 257, "retention")

    def test_control_char_rejected(self):
        with pytest.raises(ProximoError):
            _check_policy_string("a\x01b", "retention")


class TestRedactSecrets:
    def test_key_redacted(self):
        out = _redact_secrets({"key": "sekrit", "hint": "h"})
        assert out["key"] == "[redacted]"
        assert out["hint"] == "h"

    def test_password_redacted(self):
        out = _redact_secrets({"password": "sekrit"})
        assert out["password"] == "[redacted]"

    def test_new_password_hyphen_redacted(self):
        out = _redact_secrets({"new-password": "sekrit"})
        assert out["new-password"] == "[redacted]"

    def test_new_password_underscore_redacted(self):
        out = _redact_secrets({"new_password": "sekrit"})
        assert out["new_password"] == "[redacted]"

    def test_non_secret_untouched(self):
        out = _redact_secrets({"fingerprint": _FP, "kdf": "scrypt"})
        assert out["fingerprint"] == _FP
        assert out["kdf"] == "scrypt"


# ---------------------------------------------------------------------------
# Backend functions — reads
# ---------------------------------------------------------------------------

class TestTapePoolList:
    def test_calls_correct_path(self):
        api = _Api(get_return=[{"name": "pool1"}])
        result = tape_pool_list(api)
        assert api.gets == ["/config/media-pool"]
        assert result == [{"name": "pool1"}]

    def test_empty_api_returns_empty_list(self):
        api = _Api(get_return=None)
        assert tape_pool_list(api) == []


class TestTapePoolGet:
    def test_correct_path(self):
        api = _Api(get_return={"name": "pool1"})
        result = tape_pool_get(api, "pool1")
        assert api.gets == ["/config/media-pool/pool1"]
        assert result["name"] == "pool1"

    def test_invalid_name_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_pool_get(api, "a")


class TestTapeKeyList:
    def test_calls_correct_path(self):
        api = _Api(get_return=[{"fingerprint": _FP, "hint": "h", "kdf": "scrypt"}])
        result = tape_key_list(api)
        assert api.gets == ["/config/tape-encryption-keys"]
        assert result[0]["fingerprint"] == _FP
        # No secret fields returned by the fake — mirrors the live schema's PUBLIC-only shape.
        assert "password" not in result[0]
        assert "key" not in result[0]

    def test_empty_api_returns_empty_list(self):
        api = _Api(get_return=None)
        assert tape_key_list(api) == []

    def test_secret_fields_stripped_defensively(self):
        """Wave 5a review parity: the identical defensive-strip gap existed here — never trust
        the documented public-only read shape blindly (pbs_config.remote_get idiom)."""
        api = _Api(get_return=[{"fingerprint": _FP, "key": "sentinel-leaked-key",
                                "password": "sentinel-leaked-pw"}])
        result = tape_key_list(api)
        assert "key" not in result[0]
        assert "password" not in result[0]


class TestTapeKeyGet:
    def test_correct_path(self):
        api = _Api(get_return={"fingerprint": _FP, "hint": "h"})
        result = tape_key_get(api, _FP)
        assert api.gets == [f"/config/tape-encryption-keys/{_FP}"]
        assert result["fingerprint"] == _FP

    def test_secret_fields_stripped_defensively(self):
        api = _Api(get_return={"fingerprint": _FP, "key": "sentinel-leaked-key"})
        result = tape_key_get(api, _FP)
        assert "key" not in result

    def test_invalid_fingerprint_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_key_get(api, "not-a-fingerprint")


# ---------------------------------------------------------------------------
# Backend functions — mutations, Media pools
# ---------------------------------------------------------------------------

class TestTapePoolCreate:
    def test_posts_to_correct_path(self):
        api = _Api()
        tape_pool_create(api, "pool1")
        assert len(api.posts) == 1
        path, data = api.posts[0]
        assert path == "/config/media-pool"
        assert data == {"name": "pool1"}

    def test_all_fields_forwarded(self):
        api = _Api()
        tape_pool_create(
            api, "pool1", allocation="always", comment="c1", encrypt=_FP,
            retention="keep", template="tmpl-%Y",
        )
        _, data = api.posts[0]
        assert data == {
            "name": "pool1", "allocation": "always", "comment": "c1", "encrypt": _FP,
            "retention": "keep", "template": "tmpl-%Y",
        }

    def test_invalid_name_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_pool_create(api, "a")

    def test_invalid_encrypt_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_pool_create(api, "pool1", encrypt="not-a-fingerprint")

    def test_invalid_comment_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_pool_create(api, "pool1", comment="a" * 129)

    def test_invalid_template_too_short_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_pool_create(api, "pool1", template="a")


class TestTapePoolUpdate:
    def test_puts_to_correct_path(self):
        api = _Api()
        tape_pool_update(api, "pool1", allocation="continue")
        assert len(api.puts) == 1
        path, data = api.puts[0]
        assert path == "/config/media-pool/pool1"
        assert data == {"allocation": "continue"}

    def test_none_kwargs_excluded(self):
        api = _Api()
        tape_pool_update(api, "pool1")
        _, data = api.puts[0]
        assert data == {}

    def test_no_digest_param_exists(self):
        """Module docstring fact #2: media-pool PUT has NO digest param at all — tape_pool_update
        doesn't even accept one (unlike tape_pool's sibling drive/changer update in
        pbs_tape_config.py)."""
        import inspect
        sig = inspect.signature(tape_pool_update)
        assert "digest" not in sig.parameters

    def test_delete_list_forwarded(self):
        api = _Api()
        tape_pool_update(api, "pool1", delete=["allocation", "comment"])
        _, data = api.puts[0]
        assert data["delete"] == ["allocation", "comment"]

    def test_invalid_name_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_pool_update(api, "a")

    def test_invalid_retention_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_pool_update(api, "pool1", retention="")


class TestTapePoolDelete:
    def test_deletes_correct_path(self):
        api = _Api()
        tape_pool_delete(api, "pool1")
        assert api.dels[0][0] == "/config/media-pool/pool1"

    def test_no_params_sent(self):
        """Module docstring fact #2: no digest param exists on this DELETE either."""
        api = _Api()
        tape_pool_delete(api, "pool1")
        assert api.dels[0][1] is None

    def test_invalid_name_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_pool_delete(api, "a")


# ---------------------------------------------------------------------------
# Backend functions — mutations, Encryption keys
# ---------------------------------------------------------------------------

class TestTapeKeyCreate:
    def test_posts_to_correct_path_minimal(self):
        api = _Api(get_return=_FP)
        result = tape_key_create(api, "sentinel-password-value")
        assert len(api.posts) == 1
        path, data = api.posts[0]
        assert path == "/config/tape-encryption-keys"
        assert data == {"password": "sentinel-password-value"}
        assert result == _FP

    def test_all_fields_forwarded(self):
        api = _Api(get_return=_FP)
        key_material = "k" * 300
        tape_key_create(api, "sentinel-password-value", hint="h1", kdf="pbkdf2", key=key_material)
        _, data = api.posts[0]
        assert data == {
            "password": "sentinel-password-value", "hint": "h1", "kdf": "pbkdf2",
            "key": key_material,
        }

    def test_invalid_kdf_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_key_create(api, "sentinel-password-value", kdf="md5")

    def test_key_too_short_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_key_create(api, "sentinel-password-value", key="k" * 299)

    def test_key_too_long_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_key_create(api, "sentinel-password-value", key="k" * 601)

    def test_key_at_bounds_accepted(self):
        api = _Api(get_return=_FP)
        tape_key_create(api, "sentinel-password-value", key="k" * 300)
        tape_key_create(api, "sentinel-password-value", key="k" * 600)
        assert len(api.posts) == 2

    def test_invalid_hint_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_key_create(api, "sentinel-password-value", hint="a" * 65)


class TestTapeKeyUpdatePassword:
    def test_puts_to_correct_path(self):
        api = _Api()
        tape_key_update_password(api, _FP, hint="h1", new_password="sentinel-new-pw")
        assert len(api.puts) == 1
        path, data = api.puts[0]
        assert path == f"/config/tape-encryption-keys/{_FP}"
        assert data == {"hint": "h1", "new-password": "sentinel-new-pw"}

    def test_all_optional_fields_forwarded(self):
        api = _Api()
        tape_key_update_password(
            api, _FP, hint="h1", new_password="sentinel-new-pw",
            password="sentinel-old-pw", kdf="none", force=True, digest="b" * 64,
        )
        _, data = api.puts[0]
        assert data == {
            "hint": "h1", "new-password": "sentinel-new-pw", "password": "sentinel-old-pw",
            "kdf": "none", "force": True, "digest": "b" * 64,
        }

    def test_hint_and_new_password_are_required_params(self):
        """Module docstring fact #8: unlike every other PUT in this codebase, hint/new_password
        have no default — a caller MUST supply both."""
        import inspect
        sig = inspect.signature(tape_key_update_password)
        assert sig.parameters["hint"].default is inspect.Parameter.empty
        assert sig.parameters["new_password"].default is inspect.Parameter.empty

    def test_invalid_fingerprint_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_key_update_password(api, "not-a-fingerprint", hint="h1", new_password="x12345")

    def test_invalid_hint_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_key_update_password(api, _FP, hint="", new_password="x12345")

    def test_invalid_kdf_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_key_update_password(api, _FP, hint="h1", new_password="x12345", kdf="md5")

    def test_invalid_digest_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_key_update_password(api, _FP, hint="h1", new_password="x12345", digest="not-hex")


class TestTapeKeyDelete:
    def test_deletes_correct_path(self):
        api = _Api()
        tape_key_delete(api, _FP)
        assert api.dels[0][0] == f"/config/tape-encryption-keys/{_FP}"
        assert api.dels[0][1] == {}

    def test_digest_forwarded(self):
        api = _Api()
        tape_key_delete(api, _FP, digest="c" * 64)
        assert api.dels[0][1] == {"digest": "c" * 64}

    def test_invalid_digest_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_key_delete(api, _FP, digest="not-hex")

    def test_invalid_fingerprint_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            tape_key_delete(api, "not-a-fingerprint")


# ---------------------------------------------------------------------------
# Plan factories — Media pools
# ---------------------------------------------------------------------------

class TestPlanTapePoolCreate:
    def test_is_low_risk(self):
        plan = plan_tape_pool_create("pool1")
        assert plan.risk == RISK_LOW

    def test_current_is_empty(self):
        plan = plan_tape_pool_create("pool1")
        assert plan.current == {}

    def test_target_correct(self):
        plan = plan_tape_pool_create("pool1")
        assert plan.target == "pbs/config/media-pool/pool1"

    def test_change_includes_name(self):
        plan = plan_tape_pool_create("pool1", allocation="always")
        assert "pool1" in plan.change and "always" in plan.change

    def test_no_undo_primitive_implied(self):
        plan = plan_tape_pool_create("pool1")
        assert "no snapshot" in plan.note.lower()

    def test_invalid_name_raises(self):
        with pytest.raises(ProximoError):
            plan_tape_pool_create("a")

    def test_invalid_encrypt_raises(self):
        with pytest.raises(ProximoError):
            plan_tape_pool_create("pool1", encrypt="not-a-fingerprint")


class TestPlanTapePoolUpdate:
    def test_reads_current_from_api(self):
        api = _Api(get_return={"name": "pool1", "retention": "keep"})
        plan = plan_tape_pool_update(api, "pool1", allocation="always")
        assert plan.risk == RISK_MEDIUM
        assert plan.current == {"name": "pool1", "retention": "keep"}

    def test_change_includes_new_values(self):
        api = _Api(get_return={"name": "pool1"})
        plan = plan_tape_pool_update(api, "pool1", retention="overwrite")
        assert "overwrite" in plan.change

    def test_no_fields_changed_message(self):
        api = _Api(get_return={"name": "pool1"})
        plan = plan_tape_pool_update(api, "pool1")
        assert "no fields changed" in plan.change

    def test_empty_delete_list_rejected(self):
        """Wave 5b review finding 1 corrects the Wave 4a claim above: delete=[] is REJECTED, not
        disclosed — httpx's form encoding drops an empty-list value entirely, so it never
        reaches the wire."""
        api = _Api(get_return={"name": "pool1"})
        with pytest.raises(ProximoError):
            plan_tape_pool_update(api, "pool1", delete=[])

    def test_invalid_name_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            plan_tape_pool_update(api, "a")

    def test_invalid_encrypt_rejected_at_plan_time(self):
        api = _Api(get_return={"name": "pool1"})
        with pytest.raises(ProximoError):
            plan_tape_pool_update(api, "pool1", encrypt="not-a-fingerprint")

    def test_captured_current_defensively_redacted_even_when_secret_bearing(self):
        """Review finding (Wave 4b): the pool-side CAPTURE gets the same defense-in-depth
        redaction the key side already has — a secret-shaped field in an out-of-schema GET
        response must never reach Plan.current raw."""
        api = _Api(get_return={"name": "pool1", "password": "sentinel-leaked-pool-pw"})
        plan = plan_tape_pool_update(api, "pool1", allocation="always")
        assert plan.current["password"] == "[redacted]"
        assert "sentinel-leaked-pool-pw" not in str(plan.current)


class TestPlanTapePoolDelete:
    def test_is_medium_risk(self):
        """Module docstring RISK RATING note: a step UP from pbs_tape_config.py's drive/changer
        delete=LOW — losing pool config also loses retention/allocation policy + key
        association, not just an identifier."""
        api = _Api(get_return={"name": "pool1"})
        plan = plan_tape_pool_delete(api, "pool1")
        assert plan.risk == RISK_MEDIUM

    def test_reads_current_from_api(self):
        api = _Api(get_return={"name": "pool1", "retention": "keep"})
        plan = plan_tape_pool_delete(api, "pool1")
        assert plan.current == {"name": "pool1", "retention": "keep"}

    def test_captured_current_defensively_redacted_even_when_secret_bearing(self):
        """Review finding (Wave 4b) — delete-side mirror of the update-side defensive capture."""
        api = _Api(get_return={"name": "pool1", "key": "sentinel-leaked-pool-key"})
        plan = plan_tape_pool_delete(api, "pool1")
        assert plan.current["key"] == "[redacted]"
        assert "sentinel-leaked-pool-key" not in str(plan.current)

    def test_re_creatable_in_note(self):
        api = _Api(get_return={"name": "pool1"})
        plan = plan_tape_pool_delete(api, "pool1")
        assert "re-creat" in plan.note.lower()

    def test_warn_about_job_failure(self):
        api = _Api(get_return={"name": "pool1"})
        plan = plan_tape_pool_delete(api, "pool1")
        assert "WARN" in plan.note.upper()

    def test_media_data_untouched_in_blast_radius(self):
        api = _Api(get_return={"name": "pool1"})
        plan = plan_tape_pool_delete(api, "pool1")
        haystack = " ".join(plan.blast_radius).lower()
        assert "untouched" in haystack

    def test_invalid_name_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            plan_tape_pool_delete(api, "a")


# ---------------------------------------------------------------------------
# Plan factories — Encryption keys, incl. THE SECRET CONTRACT
# ---------------------------------------------------------------------------

class TestPlanTapeKeyCreate:
    def test_is_medium_risk(self):
        plan = plan_tape_key_create("sentinel-password-value")
        assert plan.risk == RISK_MEDIUM

    def test_current_is_empty(self):
        plan = plan_tape_key_create("sentinel-password-value")
        assert plan.current == {}

    def test_target_correct(self):
        plan = plan_tape_key_create("sentinel-password-value")
        assert plan.target == "pbs/config/tape-encryption-keys"

    def test_password_never_in_change(self):
        plan = plan_tape_key_create("sentinel-password-value")
        assert "sentinel-password-value" not in plan.change

    def test_key_never_in_change(self):
        key_material = "sentinel-key-material-" + "k" * 280
        plan = plan_tape_key_create("sentinel-password-value", key=key_material)
        assert key_material not in plan.change

    def test_hint_and_kdf_still_shown(self):
        """Non-secret fields are NOT redacted — only key/password."""
        plan = plan_tape_key_create("sentinel-password-value", hint="my-hint", kdf="pbkdf2")
        assert "my-hint" in plan.change
        assert "pbkdf2" in plan.change

    def test_invalid_kdf_raises(self):
        with pytest.raises(ProximoError):
            plan_tape_key_create("sentinel-password-value", kdf="md5")

    def test_key_wrong_length_raises(self):
        with pytest.raises(ProximoError):
            plan_tape_key_create("sentinel-password-value", key="short")


class TestPlanTapeKeyUpdatePassword:
    def test_is_medium_risk(self):
        api = _Api(get_return={"fingerprint": _FP, "hint": "h"})
        plan = plan_tape_key_update_password(api, _FP, hint="h2", new_password="sentinel-new-pw")
        assert plan.risk == RISK_MEDIUM

    def test_reads_current_from_api(self):
        api = _Api(get_return={"fingerprint": _FP, "hint": "old-hint"})
        plan = plan_tape_key_update_password(api, _FP, hint="h2", new_password="sentinel-new-pw")
        assert plan.current["hint"] == "old-hint"

    def test_new_password_never_in_change(self):
        api = _Api(get_return={"fingerprint": _FP})
        plan = plan_tape_key_update_password(api, _FP, hint="h2", new_password="sentinel-new-pw")
        assert "sentinel-new-pw" not in plan.change

    def test_current_password_never_in_change(self):
        api = _Api(get_return={"fingerprint": _FP})
        plan = plan_tape_key_update_password(
            api, _FP, hint="h2", new_password="sentinel-new-pw", password="sentinel-old-pw",
        )
        assert "sentinel-old-pw" not in plan.change

    def test_captured_current_defensively_redacted_even_when_secret_bearing(self):
        """Module docstring fact #9: the live schema's GET is public-only, but this module
        redacts the CAPTURE regardless (defensive-in-depth) — wire the fake GET to return a
        secret-bearing field anyway (simulating an unexpected leak) and prove it's still
        scrubbed from Plan.current."""
        api = _Api(get_return={"fingerprint": _FP, "password": "sentinel-leaked-pw"})
        plan = plan_tape_key_update_password(api, _FP, hint="h2", new_password="sentinel-new-pw")
        # Wave 5a review parity: stripped at the read layer now — stronger than redaction.
        assert "password" not in plan.current
        assert "sentinel-leaked-pw" not in str(plan.current)

    def test_invalid_fingerprint_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            plan_tape_key_update_password(api, "bad-fp", hint="h2", new_password="x12345")

    def test_bad_hint_rejected_at_plan_time(self):
        api = _Api()
        with pytest.raises(ProximoError):
            plan_tape_key_update_password(api, _FP, hint="", new_password="x12345")

    def test_bad_kdf_rejected_at_plan_time(self):
        api = _Api()
        with pytest.raises(ProximoError):
            plan_tape_key_update_password(api, _FP, hint="h2", new_password="x12345", kdf="md5")

    def test_bad_digest_rejected_at_plan_time(self):
        api = _Api()
        with pytest.raises(ProximoError, match="digest"):
            plan_tape_key_update_password(
                api, _FP, hint="h2", new_password="x12345", digest="not-a-sha256",
            )


class TestPlanTapeKeyDelete:
    def test_is_high_risk(self):
        api = _Api(get_return={"fingerprint": _FP})
        plan = plan_tape_key_delete(api, _FP)
        assert plan.risk == RISK_HIGH

    def test_unreadable_language_present_verbatim(self):
        """The campaign's HARD INVARIANT: no softening. PBS's own wording must appear."""
        api = _Api(get_return={"fingerprint": _FP})
        plan = plan_tape_key_delete(api, _FP)
        haystack = " ".join(plan.blast_radius).lower()
        assert "unreadable" in haystack
        assert "no longer access tapes using this key" in haystack

    def test_reads_current_from_api(self):
        api = _Api(get_return={"fingerprint": _FP, "hint": "h"})
        plan = plan_tape_key_delete(api, _FP)
        assert plan.current["fingerprint"] == _FP

    def test_captured_current_defensively_redacted(self):
        api = _Api(get_return={"fingerprint": _FP, "password": "sentinel-leaked-pw"})
        plan = plan_tape_key_delete(api, _FP)
        # Wave 5a review parity: stripped at the read layer now — stronger than redaction.
        assert "password" not in plan.current
        assert "sentinel-leaked-pw" not in str(plan.current)

    def test_no_undo_in_note(self):
        api = _Api(get_return={"fingerprint": _FP})
        plan = plan_tape_key_delete(api, _FP)
        assert "no undo" in plan.note.lower()

    def test_invalid_fingerprint_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            plan_tape_key_delete(api, "not-a-fingerprint")

    def test_invalid_digest_raises(self):
        api = _Api(get_return={"fingerprint": _FP})
        with pytest.raises(ProximoError):
            plan_tape_key_delete(api, _FP, digest="not-hex")
