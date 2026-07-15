"""TDD tests for the PBS ACME plane (Wave 3b, full-surface campaign) — fully mocked, no live PBS.

Mirrors test_pbs_notifications.py's style (the Wave 3a sibling): a recording fake PBS API,
validator rejection tests (\\Z-anchored), backend-function path/verb/payload tests, and
plan-factory risk/blast-radius/redaction tests.

Covers: validators (account name, plugin id, plugin type, digest, validation-delay, plugin
delete-props); backend functions for all 15 ops (7 read, 8 mutation); plan factories (risk
MEDIUM/LOW/HIGH per the module docstring's rating table, redaction of eab_hmac_key/data —
including the defensive account-side redaction and the load-bearing plugin-side redaction);
module structure.
"""

from __future__ import annotations

import pytest

from proximo.backends import ProximoError
from proximo.pbs_acme import (
    _check_acme_account_name,
    _check_acme_plugin_id,
    _check_digest,
    _check_plugin_delete_props,
    _check_plugin_type,
    _check_validation_delay,
    acme_account_create,
    acme_account_delete,
    acme_account_get,
    acme_account_list,
    acme_account_update,
    acme_cert_order,
    acme_cert_renew,
    acme_challenge_schema,
    acme_directories,
    acme_plugin_create,
    acme_plugin_delete,
    acme_plugin_get,
    acme_plugin_update,
    acme_plugins_list,
    acme_tos,
    plan_acme_account_create,
    plan_acme_account_delete,
    plan_acme_account_update,
    plan_acme_cert_order,
    plan_acme_cert_renew,
    plan_acme_plugin_create,
    plan_acme_plugin_delete,
    plan_acme_plugin_update,
)
from proximo.planning import RISK_HIGH, RISK_LOW, RISK_MEDIUM

# ---------------------------------------------------------------------------
# Recording fake
# ---------------------------------------------------------------------------

class _Api:
    """Recording fake for PbsBackend (HTTP verb tracking, no live network)."""

    def __init__(self, get_return=None):
        self._get_return = get_return
        self.gets: list[tuple[str, dict | None]] = []
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
    import proximo.pbs_acme as m
    doc = m.__doc__ or ""
    assert "revoke" in doc.lower()
    assert "eab_hmac_key" in doc


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

class TestCheckAcmeAccountName:
    def test_valid_simple(self):
        assert _check_acme_account_name("account1") == "account1"

    def test_valid_leading_underscore(self):
        """Schema's own pattern allows a leading underscore (module docstring fact #6) —
        deliberately NOT tightened to PVE's alnum-only-lead charset."""
        assert _check_acme_account_name("_acct") == "_acct"

    def test_valid_with_dot(self):
        """Schema's own pattern allows a dot anywhere in the body."""
        assert _check_acme_account_name("acct.name") == "acct.name"

    def test_valid_with_hyphen_and_underscore(self):
        assert _check_acme_account_name("acct-name_1") == "acct-name_1"

    def test_slash_raises(self):
        with pytest.raises(ProximoError):
            _check_acme_account_name("name/slash")

    def test_trailing_newline_raises(self):
        with pytest.raises(ProximoError):
            _check_acme_account_name("account1\n")

    def test_empty_raises(self):
        with pytest.raises(ProximoError):
            _check_acme_account_name("")

    def test_leading_dot_raises(self):
        with pytest.raises(ProximoError):
            _check_acme_account_name(".account")

    def test_leading_hyphen_raises(self):
        with pytest.raises(ProximoError):
            _check_acme_account_name("-account")

    def test_257_chars_raises(self):
        with pytest.raises(ProximoError):
            _check_acme_account_name("a" * 257)

    def test_256_chars_accepted(self):
        assert _check_acme_account_name("a" * 256) == "a" * 256


class TestCheckAcmePluginId:
    def test_valid_simple(self):
        assert _check_acme_plugin_id("plugin1") == "plugin1"

    def test_valid_leading_underscore(self):
        assert _check_acme_plugin_id("_plugin") == "_plugin"

    def test_min_length_one_accepted(self):
        assert _check_acme_plugin_id("a") == "a"

    def test_max_length_32_accepted(self):
        assert _check_acme_plugin_id("a" * 32) == "a" * 32

    def test_max_length_33_rejected(self):
        with pytest.raises(ProximoError):
            _check_acme_plugin_id("a" * 33)

    def test_slash_raises(self):
        with pytest.raises(ProximoError):
            _check_acme_plugin_id("plug/in")

    def test_trailing_newline_raises(self):
        with pytest.raises(ProximoError):
            _check_acme_plugin_id("plugin1\n")

    def test_empty_raises(self):
        with pytest.raises(ProximoError):
            _check_acme_plugin_id("")


class TestCheckPluginType:
    def test_valid_dns(self):
        assert _check_plugin_type("dns") == "dns"

    def test_valid_standalone(self):
        assert _check_plugin_type("standalone") == "standalone"

    def test_valid_hyphenated(self):
        assert _check_plugin_type("some-type") == "some-type"

    def test_empty_raises(self):
        with pytest.raises(ProximoError):
            _check_plugin_type("")

    def test_65_chars_rejected(self):
        with pytest.raises(ProximoError):
            _check_plugin_type("a" * 65)

    def test_slash_raises(self):
        with pytest.raises(ProximoError):
            _check_plugin_type("dns/foo")

    def test_trailing_newline_raises(self):
        with pytest.raises(ProximoError):
            _check_plugin_type("dns\n")


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


class TestCheckValidationDelay:
    def test_valid_zero(self):
        assert _check_validation_delay(0) == 0

    def test_valid_max(self):
        assert _check_validation_delay(172800) == 172800

    def test_negative_rejected(self):
        with pytest.raises(ProximoError):
            _check_validation_delay(-1)

    def test_float_rejected_not_truncated(self):
        """Review finding (Wave 3b): int(12.9) silently truncated to 12 — reject instead."""
        with pytest.raises(ProximoError):
            _check_validation_delay(12.9)  # type: ignore[arg-type]

    def test_over_max_rejected(self):
        with pytest.raises(ProximoError):
            _check_validation_delay(172801)

    def test_non_int_rejected(self):
        with pytest.raises(ProximoError):
            _check_validation_delay("not-an-int")


class TestCheckPluginDeleteProps:
    def test_valid_disable(self):
        assert _check_plugin_delete_props(["disable"]) == ["disable"]

    def test_valid_both(self):
        assert _check_plugin_delete_props(["disable", "validation-delay"]) == [
            "disable", "validation-delay",
        ]

    def test_empty_list_rejected(self):
        # Wave 5b review finding 1: `_check_plugin_delete_props` used to pass an empty list
        # straight through ("ok") — but httpx's form encoding drops an empty-list `delete`
        # value entirely, so it never reaches the wire; a silent no-op. Reject loudly instead.
        with pytest.raises(ProximoError):
            _check_plugin_delete_props([])

    def test_invalid_prop_rejected(self):
        with pytest.raises(ProximoError):
            _check_plugin_delete_props(["data"])


# ---------------------------------------------------------------------------
# Backend functions — reads
# ---------------------------------------------------------------------------

class TestAcmeAccountList:
    def test_calls_correct_path(self):
        api = _Api(get_return=[{"name": "acct1"}])
        result = acme_account_list(api)
        assert api.gets == [("/config/acme/account", None)]
        assert result == [{"name": "acct1"}]

    def test_empty_api_returns_empty_list(self):
        api = _Api(get_return=None)
        assert acme_account_list(api) == []


class TestAcmeAccountGet:
    def test_calls_correct_path(self):
        api = _Api(get_return={"directory": "https://acme.example.com"})
        result = acme_account_get(api, "acct1")
        assert api.gets == [("/config/acme/account/acct1", None)]
        assert result == {"directory": "https://acme.example.com"}

    def test_invalid_name_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            acme_account_get(api, "bad/name")


class TestAcmeDirectories:
    def test_calls_correct_path(self):
        api = _Api(get_return=[{"name": "Let's Encrypt", "url": "https://acme-v02.example.com"}])
        result = acme_directories(api)
        assert api.gets == [("/config/acme/directories", None)]
        assert result[0]["name"] == "Let's Encrypt"


class TestAcmeTos:
    def test_no_directory_omits_params(self):
        api = _Api(get_return="https://example.com/tos")
        result = acme_tos(api)
        assert api.gets == [("/config/acme/tos", None)]
        assert result == "https://example.com/tos"

    def test_directory_forwarded_as_param(self):
        api = _Api(get_return="https://example.com/tos")
        acme_tos(api, directory="https://acme-v02.example.com/directory")
        path, params = api.gets[0]
        assert path == "/config/acme/tos"
        assert params == {"directory": "https://acme-v02.example.com/directory"}

    def test_none_response_passthrough(self):
        api = _Api(get_return=None)
        assert acme_tos(api) is None

    def test_http_directory_rejected(self):
        """Review finding (Wave 3b): `directory` makes the PBS HOST fetch the URL — restrict to
        https:// (RFC 8555 requires https directories) and reject control chars/whitespace."""
        api = _Api(get_return="x")
        with pytest.raises(ProximoError, match="directory"):
            acme_tos(api, directory="http://169.254.169.254/latest/meta-data")
        assert api.gets == []

    def test_whitespace_in_directory_rejected(self):
        api = _Api(get_return="x")
        with pytest.raises(ProximoError):
            acme_tos(api, directory="https://ca.example.com/dir\n")
        assert api.gets == []

    def test_is_classified_adversarial(self):
        """The response is CA-authored (caller-chosen source) free text flowing into the agent's
        context — same channel rationale as *_apt_changelog (review finding, Wave 3b)."""
        from proximo import taint
        assert taint.is_adversarial("pbs_acme_tos")


class TestAcmeChallengeSchema:
    def test_calls_correct_path_no_params(self):
        api = _Api(get_return=[{"id": "cf", "type": "dns"}])
        result = acme_challenge_schema(api)
        assert api.gets == [("/config/acme/challenge-schema", None)]
        assert result == [{"id": "cf", "type": "dns"}]


class TestAcmePluginsList:
    def test_calls_correct_path(self):
        api = _Api(get_return=[{"plugin": "p1", "data": "LIVEDATA"}])
        result = acme_plugins_list(api)
        assert api.gets == [("/config/acme/plugins", None)]
        # backend read does NOT redact — only plan factories do (module docstring).
        assert result[0]["data"] == "LIVEDATA"


class TestAcmePluginGet:
    def test_calls_correct_path(self):
        api = _Api(get_return={"plugin": "p1", "type": "dns", "data": "LIVEDATA"})
        result = acme_plugin_get(api, "p1")
        assert api.gets == [("/config/acme/plugins/p1", None)]
        assert result["data"] == "LIVEDATA"

    def test_invalid_id_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            acme_plugin_get(api, "bad/id")


# ---------------------------------------------------------------------------
# Backend functions — mutations, Accounts
# ---------------------------------------------------------------------------

class TestAcmeAccountCreate:
    def test_posts_to_correct_path_minimal(self):
        api = _Api()
        acme_account_create(api, "mailto:a@example.com")
        assert len(api.posts) == 1
        path, data = api.posts[0]
        assert path == "/config/acme/account"
        assert data == {"contact": "mailto:a@example.com"}

    def test_optional_fields_forwarded(self):
        api = _Api()
        acme_account_create(
            api, "mailto:a@example.com", name="acct1", directory="https://d",
            eab_hmac_key="LIVEKEY", eab_kid="kid1", tos_url="https://tos",
        )
        _, data = api.posts[0]
        assert data == {
            "contact": "mailto:a@example.com", "name": "acct1", "directory": "https://d",
            "eab_hmac_key": "LIVEKEY", "eab_kid": "kid1", "tos_url": "https://tos",
        }

    def test_invalid_name_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            acme_account_create(api, "mailto:a@example.com", name="bad/name")


class TestAcmeAccountUpdate:
    def test_puts_to_correct_path(self):
        api = _Api()
        acme_account_update(api, "acct1", contact="mailto:new@example.com")
        assert len(api.puts) == 1
        path, data = api.puts[0]
        assert path == "/config/acme/account/acct1"
        assert data == {"contact": "mailto:new@example.com"}

    def test_none_contact_excluded(self):
        api = _Api()
        acme_account_update(api, "acct1")
        _, data = api.puts[0]
        assert data == {}

    def test_invalid_name_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            acme_account_update(api, "bad/name")


class TestAcmeAccountDelete:
    def test_deletes_correct_path_no_force(self):
        api = _Api()
        acme_account_delete(api, "acct1")
        assert len(api.dels) == 1
        path, params = api.dels[0]
        assert path == "/config/acme/account/acct1"
        assert params is None

    def test_force_true_forwarded(self):
        api = _Api()
        acme_account_delete(api, "acct1", force=True)
        _, params = api.dels[0]
        assert params == {"force": 1}

    def test_invalid_name_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            acme_account_delete(api, "bad/name")


# ---------------------------------------------------------------------------
# Backend functions — mutations, Plugins
# ---------------------------------------------------------------------------

class TestAcmePluginCreate:
    def test_posts_to_correct_path_full_body(self):
        backend = _Api()
        acme_plugin_create(
            backend, "plug1", "dns", api="cf", data="LIVEDATA", disable=True,
            validation_delay=60,
        )
        assert len(backend.posts) == 1
        path, body = backend.posts[0]
        assert path == "/config/acme/plugins"
        assert body == {
            "id": "plug1", "type": "dns", "api": "cf", "data": "LIVEDATA",
            "disable": True, "validation-delay": 60,
        }

    def test_minimal_body(self):
        backend = _Api()
        acme_plugin_create(backend, "plug1", "dns")
        _, body = backend.posts[0]
        assert body == {"id": "plug1", "type": "dns"}

    def test_invalid_id_raises(self):
        backend = _Api()
        with pytest.raises(ProximoError):
            acme_plugin_create(backend, "bad/id", "dns")

    def test_invalid_type_raises(self):
        backend = _Api()
        with pytest.raises(ProximoError):
            acme_plugin_create(backend, "plug1", "bad/type")

    def test_invalid_validation_delay_raises(self):
        backend = _Api()
        with pytest.raises(ProximoError):
            acme_plugin_create(backend, "plug1", "dns", validation_delay=999999)


class TestAcmePluginUpdate:
    def test_puts_to_correct_path(self):
        backend = _Api()
        acme_plugin_update(backend, "plug1", api="route53", data="NEWDATA", disable=False,
                           validation_delay=10, digest="d" * 64, delete=["disable"])
        assert len(backend.puts) == 1
        path, body = backend.puts[0]
        assert path == "/config/acme/plugins/plug1"
        assert body == {
            "api": "route53", "data": "NEWDATA", "disable": False,
            "validation-delay": 10, "digest": "d" * 64, "delete": ["disable"],
        }

    def test_none_kwargs_excluded(self):
        backend = _Api()
        acme_plugin_update(backend, "plug1")
        _, body = backend.puts[0]
        assert body == {}

    def test_invalid_digest_raises(self):
        backend = _Api()
        with pytest.raises(ProximoError):
            acme_plugin_update(backend, "plug1", digest="not-hex")

    def test_invalid_delete_prop_raises(self):
        backend = _Api()
        with pytest.raises(ProximoError):
            acme_plugin_update(backend, "plug1", delete=["data"])

    def test_empty_delete_list_rejected(self):
        # Wave 5b review finding 1: httpx's form encoding drops an empty-list `delete` value
        # entirely on the PUT — an empty list is a silent no-op, so reject it loudly instead.
        backend = _Api()
        with pytest.raises(ProximoError):
            acme_plugin_update(backend, "plug1", delete=[])
        assert not backend.puts


class TestAcmePluginDelete:
    def test_deletes_correct_path(self):
        api = _Api()
        acme_plugin_delete(api, "plug1")
        assert api.dels[0][0] == "/config/acme/plugins/plug1"

    def test_invalid_id_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            acme_plugin_delete(api, "bad/id")


# ---------------------------------------------------------------------------
# Backend functions — mutations, cert order/renew
# ---------------------------------------------------------------------------

class TestAcmeCertOrder:
    def test_posts_default_node_no_force(self):
        api = _Api()
        acme_cert_order(api)
        assert len(api.posts) == 1
        path, data = api.posts[0]
        assert path == "/nodes/localhost/certificates/acme/certificate"
        assert data == {}

    def test_force_true_sends_force_1(self):
        api = _Api()
        acme_cert_order(api, node="pbs1", force=True)
        path, data = api.posts[0]
        assert path == "/nodes/pbs1/certificates/acme/certificate"
        assert data == {"force": 1}

    def test_invalid_node_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            acme_cert_order(api, node="bad/node")


class TestAcmeCertRenew:
    def test_puts_default_node_no_force(self):
        api = _Api()
        acme_cert_renew(api)
        assert len(api.puts) == 1
        path, data = api.puts[0]
        assert path == "/nodes/localhost/certificates/acme/certificate"
        assert data == {}

    def test_force_true_sends_force_1(self):
        api = _Api()
        acme_cert_renew(api, node="pbs1", force=True)
        path, data = api.puts[0]
        assert path == "/nodes/pbs1/certificates/acme/certificate"
        assert data == {"force": 1}


# ---------------------------------------------------------------------------
# Plan factories — Accounts
# ---------------------------------------------------------------------------

class TestPlanAcmeAccountCreate:
    def test_is_medium_risk(self):
        plan = plan_acme_account_create("mailto:a@example.com")
        assert plan.risk == RISK_MEDIUM

    def test_current_is_empty(self):
        plan = plan_acme_account_create("mailto:a@example.com")
        assert plan.current == {}

    def test_target_uses_name_when_given(self):
        plan = plan_acme_account_create("mailto:a@example.com", name="acct1")
        assert plan.target == "pbs/config/acme/account/acct1"

    def test_target_falls_back_to_collection_when_no_name(self):
        plan = plan_acme_account_create("mailto:a@example.com")
        assert plan.target == "pbs/config/acme/account"

    def test_redacts_eab_hmac_key_from_change(self):
        plan = plan_acme_account_create("mailto:a@example.com", eab_hmac_key="LIVEKEY")
        assert "LIVEKEY" not in plan.change
        assert "[redacted]" in plan.change

    def test_invalid_name_raises(self):
        with pytest.raises(ProximoError):
            plan_acme_account_create("mailto:a@example.com", name="bad/name")

    def test_http_directory_rejected_at_plan_time(self):
        with pytest.raises(ProximoError, match="directory"):
            plan_acme_account_create("mailto:a@example.com", directory="http://ca.example.com")

    def test_http_tos_url_rejected_at_plan_time(self):
        with pytest.raises(ProximoError, match="tos_url"):
            plan_acme_account_create("mailto:a@example.com", tos_url="http://ca.example.com/tos")


class TestPlanAcmeAccountUpdate:
    def test_reads_current_from_api(self):
        api = _Api(get_return={"directory": "https://d"})
        plan = plan_acme_account_update(api, "acct1")
        assert plan.risk == RISK_LOW
        assert "directory" in plan.current

    def test_defensively_redacts_eab_hmac_key_from_current(self):
        """The live schema never actually returns eab_hmac_key on GET (module docstring fact
        #4), but this plan factory redacts it anyway if present — defensive, not load-bearing
        against a REAL PBS today, but proven here in case a fake/future API ever returns it."""
        api = _Api(get_return={"directory": "https://d", "eab_hmac_key": "LIVEKEY"})
        plan = plan_acme_account_update(api, "acct1")
        assert "LIVEKEY" not in str(plan.current)
        assert plan.current["eab_hmac_key"] == "[redacted]"

    def test_no_implied_undo_in_note(self):
        api = _Api(get_return={})
        plan = plan_acme_account_update(api, "acct1")
        assert "re-apply" in plan.note.lower() or "no snapshot" in plan.note.lower()


class TestPlanAcmeAccountDelete:
    def test_is_high_risk(self):
        api = _Api(get_return={})
        plan = plan_acme_account_delete(api, "acct1")
        assert plan.risk == RISK_HIGH

    def test_irreversible_in_change(self):
        api = _Api(get_return={})
        plan = plan_acme_account_delete(api, "acct1")
        assert "IRREVERSIBLE" in plan.change

    def test_defensively_redacts_eab_hmac_key_from_current(self):
        api = _Api(get_return={"eab_hmac_key": "LIVEKEY"})
        plan = plan_acme_account_delete(api, "acct1")
        assert "LIVEKEY" not in str(plan.current)

    def test_force_note_included_when_true(self):
        api = _Api(get_return={})
        plan = plan_acme_account_delete(api, "acct1", force=True)
        assert "force" in plan.change.lower()

    def test_force_note_absent_when_false(self):
        api = _Api(get_return={})
        plan = plan_acme_account_delete(api, "acct1", force=False)
        assert "(force:" not in plan.change


# ---------------------------------------------------------------------------
# Plan factories — Plugins
# ---------------------------------------------------------------------------

class TestPlanAcmePluginCreate:
    def test_is_medium_risk(self):
        plan = plan_acme_plugin_create("plug1", "dns")
        assert plan.risk == RISK_MEDIUM

    def test_current_is_empty(self):
        plan = plan_acme_plugin_create("plug1", "dns")
        assert plan.current == {}

    def test_target_correct(self):
        plan = plan_acme_plugin_create("plug1", "dns")
        assert plan.target == "pbs/config/acme/plugins/plug1"

    def test_redacts_data_from_change(self):
        plan = plan_acme_plugin_create("plug1", "dns", data="LIVEDATA")
        assert "LIVEDATA" not in plan.change
        assert "[redacted]" in plan.change

    def test_invalid_id_raises(self):
        with pytest.raises(ProximoError):
            plan_acme_plugin_create("bad/id", "dns")

    def test_invalid_type_raises(self):
        with pytest.raises(ProximoError):
            plan_acme_plugin_create("plug1", "bad/type")

    def test_out_of_range_validation_delay_rejected_at_plan_time(self):
        """Review finding (Wave 3b): the dry-run preview must fail on a value the execution side
        would reject — same early-validation contract as digest/delete."""
        with pytest.raises(ProximoError, match="validation-delay"):
            plan_acme_plugin_create("plug1", "dns", validation_delay=999999)


class TestPlanAcmePluginUpdate:
    def test_reads_current_from_api(self):
        backend = _Api(get_return={"plugin": "plug1", "type": "dns"})
        plan = plan_acme_plugin_update(backend, "plug1")
        assert plan.risk == RISK_MEDIUM
        assert "plugin" in plan.current

    def test_out_of_range_validation_delay_rejected_at_plan_time(self):
        backend = _Api(get_return={"plugin": "plug1", "type": "dns"})
        with pytest.raises(ProximoError, match="validation-delay"):
            plan_acme_plugin_update(backend, "plug1", validation_delay=999999)

    def test_redacts_data_from_current(self):
        """Load-bearing (module docstring fact #4) — a live PBS DOES return `data` on plugin
        GET, unlike account's eab_hmac_key."""
        backend = _Api(get_return={"plugin": "plug1", "data": "LIVEDATA"})
        plan = plan_acme_plugin_update(backend, "plug1")
        assert "LIVEDATA" not in str(plan.current)
        assert plan.current["data"] == "[redacted]"

    def test_redacts_data_from_change(self):
        backend = _Api(get_return={})
        plan = plan_acme_plugin_update(backend, "plug1", data="NEWDATA")
        assert "NEWDATA" not in plan.change
        assert "[redacted]" in plan.change

    def test_bad_digest_rejected_at_plan_time(self):
        backend = _Api(get_return={})
        with pytest.raises(ProximoError, match="digest"):
            plan_acme_plugin_update(backend, "plug1", digest="not-a-sha256")

    def test_bad_delete_prop_rejected_at_plan_time(self):
        backend = _Api(get_return={})
        with pytest.raises(ProximoError):
            plan_acme_plugin_update(backend, "plug1", delete=["data"])

    def test_empty_delete_list_rejected_at_plan_time(self):
        # Wave 5b review finding 1: delete=[] is REJECTED, not disclosed.
        backend = _Api(get_return={})
        with pytest.raises(ProximoError):
            plan_acme_plugin_update(backend, "plug1", delete=[])

    def test_no_implied_undo_in_note(self):
        backend = _Api(get_return={})
        plan = plan_acme_plugin_update(backend, "plug1")
        assert "no snapshot" in plan.note.lower() or "re-apply" in plan.note.lower()


class TestPlanAcmePluginDelete:
    def test_is_high_risk(self):
        api = _Api(get_return={})
        plan = plan_acme_plugin_delete(api, "plug1")
        assert plan.risk == RISK_HIGH

    def test_redacts_data_from_current(self):
        api = _Api(get_return={"plugin": "plug1", "data": "LIVEDATA"})
        plan = plan_acme_plugin_delete(api, "plug1")
        assert "LIVEDATA" not in str(plan.current)
        assert plan.current["data"] == "[redacted]"


# ---------------------------------------------------------------------------
# Plan factories — cert order/renew
# ---------------------------------------------------------------------------

class TestPlanAcmeCertOrder:
    def test_is_medium_risk(self):
        plan = plan_acme_cert_order()
        assert plan.risk == RISK_MEDIUM

    def test_current_is_empty(self):
        plan = plan_acme_cert_order()
        assert plan.current == {}

    def test_target_includes_node(self):
        plan = plan_acme_cert_order(node="pbs1")
        assert "pbs1" in plan.target

    def test_note_mentions_no_revoke(self):
        plan = plan_acme_cert_order()
        assert "revoke" in plan.note.lower()

    def test_note_mentions_no_upid(self):
        plan = plan_acme_cert_order()
        assert "upid" in plan.note.lower()


class TestPlanAcmeCertRenew:
    def test_is_medium_risk(self):
        plan = plan_acme_cert_renew()
        assert plan.risk == RISK_MEDIUM

    def test_target_includes_node(self):
        plan = plan_acme_cert_renew(node="pbs1")
        assert "pbs1" in plan.target

    def test_force_reflected_in_change(self):
        plan = plan_acme_cert_renew(force=True)
        assert "force" in plan.change.lower()
