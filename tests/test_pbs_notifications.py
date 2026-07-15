"""TDD tests for the PBS notifications plane (Wave 3a, full-surface campaign) — fully mocked,
no live PBS.

Mirrors test_notifications.py's style (the PVE sibling): a recording fake PBS API, validator
rejection tests (\\Z-anchored), backend-function path/verb/payload tests, and plan-factory
risk/blast-radius/redaction tests.

Covers: validators (endpoint type, notification name, matcher mode, digest); backend functions
for all 13 ops (7 read, 6 mutation); plan factories (risk LOW across the board, redaction of the
WIDER {token,password,secret,header} secret set — including the deliberate fix over the PVE
precedent that leaves plan_notification_endpoint_delete's `current` unredacted); module structure.
"""

from __future__ import annotations

import pytest

from proximo.backends import ProximoError
from proximo.pbs_notifications import (
    _check_digest,
    _check_endpoint_type,
    _check_matcher_mode,
    _check_notification_name,
    notification_endpoint_create,
    notification_endpoint_delete,
    notification_endpoint_get,
    notification_endpoint_list,
    notification_endpoint_update,
    notification_matcher_delete,
    notification_matcher_field_values,
    notification_matcher_fields,
    notification_matcher_get,
    notification_matcher_set,
    notification_matchers_list,
    notification_target_test,
    notification_targets_list,
    plan_notification_endpoint_create,
    plan_notification_endpoint_delete,
    plan_notification_endpoint_update,
    plan_notification_matcher_delete,
    plan_notification_matcher_set,
    plan_notification_target_test,
)
from proximo.planning import RISK_LOW

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
    import proximo.pbs_notifications as m
    doc = m.__doc__ or ""
    assert "directory index" in doc.lower()
    assert "secret" in doc.lower()


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

class TestCheckEndpointType:
    def test_valid_all_four(self):
        for t in ("gotify", "sendmail", "smtp", "webhook"):
            assert _check_endpoint_type(t) == t

    def test_invalid_raises(self):
        with pytest.raises(ProximoError, match="invalid PBS notification endpoint type"):
            _check_endpoint_type("slack")

    def test_uppercase_raises(self):
        with pytest.raises(ProximoError):
            _check_endpoint_type("SMTP")

    def test_empty_raises(self):
        with pytest.raises(ProximoError):
            _check_endpoint_type("")


class TestCheckNotificationName:
    def test_valid_simple(self):
        assert _check_notification_name("mail1") == "mail1"

    def test_valid_with_hyphen_and_underscore(self):
        assert _check_notification_name("alert-smtp_1") == "alert-smtp_1"

    def test_min_length_two_enforced(self):
        with pytest.raises(ProximoError):
            _check_notification_name("a")

    def test_max_length_32_enforced(self):
        with pytest.raises(ProximoError):
            _check_notification_name("a" * 33)

    def test_max_length_32_accepted(self):
        assert _check_notification_name("a" * 32) == "a" * 32

    def test_dot_rejected(self):
        """PBS's own schema pattern allows dots; this module's validator is STRICTER (mirrors
        PVE notifications.py's charset) and rejects them — see module docstring fact #7."""
        with pytest.raises(ProximoError):
            _check_notification_name("mail.name")

    def test_leading_underscore_rejected(self):
        """PBS's own schema pattern allows a leading underscore; stricter here (alnum-lead only,
        matching PVE's charset) — see module docstring fact #7."""
        with pytest.raises(ProximoError):
            _check_notification_name("_mail1")

    def test_slash_raises(self):
        with pytest.raises(ProximoError):
            _check_notification_name("name/slash")

    def test_trailing_newline_raises(self):
        with pytest.raises(ProximoError):
            _check_notification_name("mail1\n")

    def test_empty_raises(self):
        with pytest.raises(ProximoError):
            _check_notification_name("")

    def test_control_char_raises(self):
        with pytest.raises(ProximoError):
            _check_notification_name("ma\x00il1")


class TestCheckMatcherMode:
    def test_valid_all(self):
        assert _check_matcher_mode("all") == "all"

    def test_valid_any(self):
        assert _check_matcher_mode("any") == "any"

    def test_invalid_raises(self):
        with pytest.raises(ProximoError, match="invalid PBS matcher mode"):
            _check_matcher_mode("majority")


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


# ---------------------------------------------------------------------------
# Backend functions — reads
# ---------------------------------------------------------------------------

class TestNotificationTargetsList:
    def test_calls_correct_path(self):
        api = _Api(get_return=[{"name": "mail1", "type": "smtp"}])
        result = notification_targets_list(api)
        assert api.gets == ["/config/notifications/targets"]
        assert result == [{"name": "mail1", "type": "smtp"}]

    def test_empty_api_returns_empty_list(self):
        api = _Api(get_return=None)
        assert notification_targets_list(api) == []


class TestNotificationEndpointList:
    def test_no_filter_aggregates_all_four_types(self):
        api = _Api(get_return=[{"name": "x"}])
        result = notification_endpoint_list(api)
        assert api.gets == [
            "/config/notifications/endpoints/gotify",
            "/config/notifications/endpoints/sendmail",
            "/config/notifications/endpoints/smtp",
            "/config/notifications/endpoints/webhook",
        ]
        # 4 types x one item each, each tagged with its type
        assert len(result) == 4
        assert {item["type"] for item in result} == {"gotify", "sendmail", "smtp", "webhook"}

    def test_filter_by_type_calls_only_that_path(self):
        api = _Api(get_return=[{"name": "hook1"}])
        result = notification_endpoint_list(api, ep_type="webhook")
        assert api.gets == ["/config/notifications/endpoints/webhook"]
        assert result == [{"name": "hook1", "type": "webhook"}]

    def test_existing_type_field_not_overwritten(self):
        api = _Api(get_return=[{"name": "hook1", "type": "custom"}])
        result = notification_endpoint_list(api, ep_type="webhook")
        assert result[0]["type"] == "custom"

    def test_invalid_type_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            notification_endpoint_list(api, ep_type="slack")

    def test_empty_per_type_response_handled(self):
        api = _Api(get_return=None)
        result = notification_endpoint_list(api, ep_type="gotify")
        assert result == []


class TestNotificationEndpointGet:
    def test_correct_path(self):
        api = _Api(get_return={"name": "mail1", "server": "smtp.example.com"})
        result = notification_endpoint_get(api, "smtp", "mail1")
        assert api.gets == ["/config/notifications/endpoints/smtp/mail1"]
        assert result["name"] == "mail1"

    def test_invalid_type_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            notification_endpoint_get(api, "slack", "n1")

    def test_invalid_name_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            notification_endpoint_get(api, "smtp", "name/slash")


class TestNotificationMatchersList:
    def test_calls_correct_path(self):
        api = _Api(get_return=[{"name": "m1"}])
        result = notification_matchers_list(api)
        assert api.gets == ["/config/notifications/matchers"]
        assert result == [{"name": "m1"}]


class TestNotificationMatcherGet:
    def test_correct_path(self):
        api = _Api(get_return={"name": "m1"})
        result = notification_matcher_get(api, "m1")
        assert api.gets == ["/config/notifications/matchers/m1"]
        assert result == {"name": "m1"}

    def test_invalid_name_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            notification_matcher_get(api, "bad/name")


class TestNotificationMatcherFields:
    def test_calls_correct_path_no_params(self):
        api = _Api(get_return=[{"name": "severity"}])
        result = notification_matcher_fields(api)
        assert api.gets == ["/config/notifications/matcher-fields"]
        assert result == [{"name": "severity"}]


class TestNotificationMatcherFieldValues:
    def test_calls_correct_path_no_params(self):
        api = _Api(get_return=[{"field": "severity", "value": "error"}])
        result = notification_matcher_field_values(api)
        assert api.gets == ["/config/notifications/matcher-field-values"]
        assert result == [{"field": "severity", "value": "error"}]


# ---------------------------------------------------------------------------
# Backend functions — mutations, Endpoints
# ---------------------------------------------------------------------------

class TestNotificationEndpointCreate:
    def test_posts_to_correct_path_name_in_body(self):
        api = _Api()
        notification_endpoint_create(api, "smtp", "mail1", server="smtp.example.com")
        assert len(api.posts) == 1
        path, data = api.posts[0]
        assert path == "/config/notifications/endpoints/smtp"
        assert data["name"] == "mail1"
        assert data["server"] == "smtp.example.com"

    def test_none_kwargs_excluded(self):
        api = _Api()
        notification_endpoint_create(api, "smtp", "mail1", server=None)
        _, data = api.posts[0]
        assert "server" not in data

    def test_invalid_type_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            notification_endpoint_create(api, "discord", "n1")

    def test_invalid_name_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            notification_endpoint_create(api, "smtp", "bad/name")


class TestNotificationEndpointUpdate:
    def test_puts_to_correct_path(self):
        api = _Api()
        notification_endpoint_update(api, "smtp", "mail1", server="smtp2.example.com")
        assert len(api.puts) == 1
        path, data = api.puts[0]
        assert path == "/config/notifications/endpoints/smtp/mail1"
        assert data["server"] == "smtp2.example.com"

    def test_none_kwargs_excluded(self):
        api = _Api()
        notification_endpoint_update(api, "smtp", "mail1", server=None)
        _, data = api.puts[0]
        assert "server" not in data

    def test_digest_forwarded_and_validated(self):
        api = _Api()
        digest = "b" * 64
        notification_endpoint_update(api, "smtp", "mail1", digest=digest)
        _, data = api.puts[0]
        assert data["digest"] == digest

    def test_invalid_digest_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            notification_endpoint_update(api, "smtp", "mail1", digest="not-hex")

    def test_invalid_type_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            notification_endpoint_update(api, "slack", "n1")


class TestNotificationEndpointDelete:
    def test_deletes_correct_path(self):
        api = _Api()
        notification_endpoint_delete(api, "smtp", "mail1")
        assert api.dels[0][0] == "/config/notifications/endpoints/smtp/mail1"

    def test_invalid_type_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            notification_endpoint_delete(api, "badtype", "n1")


# ---------------------------------------------------------------------------
# Backend functions — mutations, Matchers
# ---------------------------------------------------------------------------

class TestNotificationMatcherSet:
    # Schema-verified 2026-07-15: /config/notifications/matchers/{name} accepts GET/PUT/DELETE
    # only; create is POST on the collection with the name in the body.

    def test_create_posts_to_collection_with_name_in_body(self):
        api = _Api(get_return=[])  # matcher does not exist yet
        notification_matcher_set(api, "all-alerts", comment="route all")
        assert api.gets == ["/config/notifications/matchers"]
        assert len(api.posts) == 1 and not api.puts
        path, data = api.posts[0]
        assert path == "/config/notifications/matchers"
        assert data["name"] == "all-alerts"
        assert data["comment"] == "route all"

    def test_update_puts_to_name_path(self):
        api = _Api(get_return=[{"name": "all-alerts"}])  # matcher already exists
        notification_matcher_set(api, "all-alerts", comment="route all")
        assert len(api.puts) == 1 and not api.posts
        path, data = api.puts[0]
        assert path == "/config/notifications/matchers/all-alerts"
        assert data["comment"] == "route all"
        assert "name" not in data

    def test_digest_and_delete_only_sent_on_update(self):
        api = _Api(get_return=[{"name": "m1"}])
        notification_matcher_set(api, "m1", digest="c" * 64, delete=["comment"])
        _, data = api.puts[0]
        assert data["digest"] == "c" * 64
        assert data["delete"] == ["comment"]

    def test_digest_and_delete_dropped_on_create(self):
        api = _Api(get_return=[])
        notification_matcher_set(api, "m1", digest="c" * 64, delete=["comment"])
        _, data = api.posts[0]
        assert "digest" not in data
        assert "delete" not in data

    def test_hyphenated_fields_mapped(self):
        api = _Api(get_return=[])
        notification_matcher_set(
            api, "m1", mode="any", match_severity=["error"], match_field=["type=x"],
            match_calendar=["*-*-* 08:00"], invert_match=True, target=["ep1"], disable=True,
        )
        _, data = api.posts[0]
        assert data["mode"] == "any"
        assert data["match-severity"] == ["error"]
        assert data["match-field"] == ["type=x"]
        assert data["match-calendar"] == ["*-*-* 08:00"]
        assert data["invert-match"] is True
        assert data["target"] == ["ep1"]
        assert data["disable"] is True

    def test_invalid_mode_raises(self):
        api = _Api(get_return=[])
        with pytest.raises(ProximoError):
            notification_matcher_set(api, "m1", mode="majority")

    def test_none_kwargs_excluded(self):
        api = _Api(get_return=[])
        notification_matcher_set(api, "matcher1", comment=None)
        _, data = api.posts[0]
        assert "comment" not in data

    def test_invalid_name_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            notification_matcher_set(api, "bad/name")


class TestNotificationMatcherDelete:
    def test_deletes_correct_path(self):
        api = _Api()
        notification_matcher_delete(api, "all-alerts")
        assert api.dels[0][0] == "/config/notifications/matchers/all-alerts"

    def test_invalid_name_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            notification_matcher_delete(api, "bad/name")


# ---------------------------------------------------------------------------
# Backend function — Target Test
# ---------------------------------------------------------------------------

class TestNotificationTargetTest:
    def test_posts_to_correct_path_no_body(self):
        api = _Api()
        notification_target_test(api, "smtp1")
        assert len(api.posts) == 1
        path, data = api.posts[0]
        assert path == "/config/notifications/targets/smtp1/test"
        assert data is None

    def test_invalid_name_raises(self):
        api = _Api()
        with pytest.raises(ProximoError):
            notification_target_test(api, "bad/name")


# ---------------------------------------------------------------------------
# Plan factories — Endpoints
# ---------------------------------------------------------------------------

class TestPlanNotificationEndpointCreate:
    def test_is_low_risk(self):
        plan = plan_notification_endpoint_create("smtp", "mail1")
        assert plan.risk == RISK_LOW

    def test_current_is_empty(self):
        plan = plan_notification_endpoint_create("smtp", "mail1")
        assert plan.current == {}

    def test_target_correct(self):
        plan = plan_notification_endpoint_create("gotify", "gotify1")
        assert plan.target == "pbs/config/notifications/endpoints/gotify/gotify1"

    def test_change_includes_type_and_name(self):
        plan = plan_notification_endpoint_create("smtp", "mail1")
        assert "smtp" in plan.change and "mail1" in plan.change

    def test_invalid_type_raises(self):
        with pytest.raises(ProximoError):
            plan_notification_endpoint_create("slack", "n1")

    def test_invalid_name_raises(self):
        with pytest.raises(ProximoError):
            plan_notification_endpoint_create("smtp", "bad/name")

    def test_redacts_token_from_change(self):
        plan = plan_notification_endpoint_create("gotify", "gotify1", token="LIVETOKEN")
        assert "LIVETOKEN" not in plan.change
        assert "[redacted]" in plan.change

    def test_redacts_password_from_change(self):
        plan = plan_notification_endpoint_create("smtp", "mail1", password="LIVEPW")
        assert "LIVEPW" not in plan.change
        assert "[redacted]" in plan.change

    def test_redacts_webhook_secret_from_change(self):
        plan = plan_notification_endpoint_create(
            "webhook", "hook1", url="https://example.com",
            secret=[{"name": "auth", "value": "LIVESECRETVALUE"}],
        )
        assert "LIVESECRETVALUE" not in plan.change
        assert "[redacted]" in plan.change

    def test_redacts_webhook_header_from_change(self):
        """Header is NOT flagged secret by PBS's own schema, but can carry an Authorization
        value — this module redacts it anyway (module docstring fact #3, wider than PVE)."""
        plan = plan_notification_endpoint_create(
            "webhook", "hook1", url="https://example.com",
            header=[{"name": "Authorization", "value": "TOPSECRETHEADERVALUE"}],
        )
        assert "TOPSECRETHEADERVALUE" not in plan.change
        assert "[redacted]" in plan.change


class TestPlanNotificationEndpointUpdate:
    def test_reads_current_from_api(self):
        api = _Api(get_return={"name": "mail1", "server": "smtp.example.com"})
        plan = plan_notification_endpoint_update(api, "smtp", "mail1")
        assert plan.risk == RISK_LOW
        assert "name" in plan.current

    def test_redacts_token_from_current(self):
        api = _Api(get_return={"name": "gotify1", "token": "LIVETOKEN"})
        plan = plan_notification_endpoint_update(api, "gotify", "gotify1", server="new-host")
        assert "LIVETOKEN" not in str(plan.current)
        assert plan.current["token"] == "[redacted]"

    def test_redacts_token_from_change(self):
        api = _Api(get_return={"name": "gotify1"})
        plan = plan_notification_endpoint_update(api, "gotify", "gotify1", token="NEWTOKEN")
        assert "NEWTOKEN" not in plan.change
        assert "[redacted]" in plan.change

    def test_redacts_header_from_current(self):
        """The webhook GET response schema DOES include header values (unlike `secret`, which
        PBS documents as value-stripped on read) — this is exactly why header must be redacted
        from Plan.current too, not just Plan.change (module docstring fact #4)."""
        api = _Api(get_return={
            "name": "hook1",
            "header": [{"name": "Authorization", "value": "TOPSECRETHEADERVALUE"}],
        })
        plan = plan_notification_endpoint_update(api, "webhook", "hook1")
        assert "TOPSECRETHEADERVALUE" not in str(plan.current)
        assert plan.current["header"] == "[redacted]"

    def test_no_implied_undo_in_note(self):
        api = _Api(get_return={"name": "mail1"})
        plan = plan_notification_endpoint_update(api, "smtp", "mail1")
        note_lower = plan.note.lower()
        assert "no snapshot" in note_lower or "no undo" in note_lower or "re-apply" in note_lower

    def test_bad_digest_rejected_at_plan_time(self):
        """A malformed digest must fail at PLAN build, not only on confirm=True — same
        early-validation contract plan_notification_matcher_set already documents (review
        finding, Wave 3a)."""
        api = _Api(get_return={"name": "mail1"})
        with pytest.raises(ProximoError, match="digest"):
            plan_notification_endpoint_update(api, "smtp", "mail1", digest="not-a-sha256")


class TestPlanNotificationEndpointDelete:
    def test_reads_current_from_api(self):
        api = _Api(get_return={"name": "mail1", "server": "smtp.example.com"})
        plan = plan_notification_endpoint_delete(api, "smtp", "mail1")
        assert plan.risk == RISK_LOW
        assert "name" in plan.current

    def test_redacts_header_from_current(self):
        """Deliberate fix over the PVE precedent: PVE's plan_notification_endpoint_delete does
        NOT redact `current` at all (module docstring fact #4). This module does."""
        api = _Api(get_return={
            "name": "hook1",
            "header": [{"name": "Authorization", "value": "TOPSECRETHEADERVALUE"}],
        })
        plan = plan_notification_endpoint_delete(api, "webhook", "hook1")
        assert "TOPSECRETHEADERVALUE" not in str(plan.current)
        assert plan.current["header"] == "[redacted]"

    def test_warn_about_silent_failure(self):
        api = _Api(get_return={"name": "mail1"})
        plan = plan_notification_endpoint_delete(api, "smtp", "mail1")
        note_upper = plan.note.upper()
        assert "WARN" in note_upper


# ---------------------------------------------------------------------------
# Plan factories — Matchers
# ---------------------------------------------------------------------------

class TestPlanNotificationMatcherSet:
    def test_is_low_risk(self):
        plan = plan_notification_matcher_set("all-alerts")
        assert plan.risk == RISK_LOW

    def test_current_is_empty(self):
        plan = plan_notification_matcher_set("all-alerts")
        assert plan.current == {}

    def test_change_includes_hyphenated_field_names(self):
        plan = plan_notification_matcher_set("m1", match_severity=["error"], invert_match=True)
        assert "match-severity" in plan.change
        assert "invert-match" in plan.change

    def test_invalid_name_raises(self):
        with pytest.raises(ProximoError):
            plan_notification_matcher_set("bad/name")

    def test_invalid_mode_raises(self):
        with pytest.raises(ProximoError):
            plan_notification_matcher_set("m1", mode="majority")

    def test_invalid_digest_raises(self):
        with pytest.raises(ProximoError):
            plan_notification_matcher_set("m1", digest="not-hex")


class TestPlanNotificationMatcherDelete:
    def test_is_low_risk(self):
        plan = plan_notification_matcher_delete("all-alerts")
        assert plan.risk == RISK_LOW

    def test_warn_in_note(self):
        plan = plan_notification_matcher_delete("all-alerts")
        assert "WARN" in plan.note.upper()

    def test_invalid_name_raises(self):
        with pytest.raises(ProximoError):
            plan_notification_matcher_delete("bad/name")


# ---------------------------------------------------------------------------
# Plan factory — Target Test
# ---------------------------------------------------------------------------

class TestPlanNotificationTargetTest:
    def test_is_low_risk(self):
        plan = plan_notification_target_test("smtp1")
        assert plan.risk == RISK_LOW

    def test_current_is_empty(self):
        plan = plan_notification_target_test("smtp1")
        assert plan.current == {}

    def test_change_mentions_real_test_notification(self):
        plan = plan_notification_target_test("smtp1")
        assert "test" in plan.change.lower()
        assert "REAL" in plan.change

    def test_invalid_name_raises(self):
        with pytest.raises(ProximoError):
            plan_notification_target_test("bad/name")
