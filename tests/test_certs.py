"""Tests for acme_certs.py — PVE ACME account and plugin CRUD.

Coverage:
  - Validator: trailing-newline bypass rejected (\\Z anchor), slash rejected
  - Operations: correct HTTP verb, path, and body shape (id/name in body for creates)
  - Plan factories: risk levels, blast_radius, honesty notes
    - account_delete / plugin_delete: HIGH + IRREVERSIBLE + TLS-lockout blast_radius
    - account_update: LOW risk
    - account_create / plugin_create / plugin_update: MEDIUM risk
"""

from __future__ import annotations

import pytest

from proximo.acme_certs import (
    _check_acme_account_name,
    _check_acme_plugin_id,
    acme_account_create,
    acme_account_delete,
    acme_account_get,
    acme_account_update,
    acme_plugin_create,
    acme_plugin_delete,
    acme_plugin_get,
    acme_plugin_update,
    plan_acme_account_create,
    plan_acme_account_delete,
    plan_acme_account_update,
    plan_acme_plugin_create,
    plan_acme_plugin_delete,
    plan_acme_plugin_update,
)
from proximo.backends import ProximoError
from proximo.planning import RISK_HIGH, RISK_LOW, RISK_MEDIUM

# ---------------------------------------------------------------------------
# Recording fake API
# ---------------------------------------------------------------------------

class _Api:
    """Recording fake: captures all calls for assertion."""

    def __init__(self, get_returns: dict | None = None):
        self.gets: list[str] = []
        self.posts: list[tuple[str, dict]] = []
        self.puts: list[tuple[str, dict]] = []
        self.dels: list[str] = []
        self._get_returns: dict = get_returns or {}

    def _get(self, path: str):
        self.gets.append(path)
        return self._get_returns.get(path)

    def _post(self, path: str, data: dict | None = None):
        self.posts.append((path, data or {}))

    def _put(self, path: str, data: dict | None = None):
        self.puts.append((path, data or {}))

    def _delete(self, path: str):
        self.dels.append(path)


# ---------------------------------------------------------------------------
# Validator tests
# ---------------------------------------------------------------------------

class TestCheckAcmeAccountName:
    def test_valid_simple(self):
        assert _check_acme_account_name("default") == "default"

    def test_valid_with_hyphen(self):
        assert _check_acme_account_name("letsencrypt-prod") == "letsencrypt-prod"

    def test_valid_with_underscore(self):
        assert _check_acme_account_name("my_account") == "my_account"

    def test_rejects_trailing_newline(self):
        # \\Z anchor — newline after valid name must be rejected
        with pytest.raises(ProximoError, match="invalid ACME account name"):
            _check_acme_account_name("default\n")

    def test_rejects_slash(self):
        with pytest.raises(ProximoError, match="invalid ACME account name"):
            _check_acme_account_name("my/account")

    def test_rejects_empty(self):
        with pytest.raises(ProximoError, match="invalid ACME account name"):
            _check_acme_account_name("")

    def test_rejects_leading_hyphen(self):
        with pytest.raises(ProximoError, match="invalid ACME account name"):
            _check_acme_account_name("-bad")

    def test_rejects_too_long(self):
        with pytest.raises(ProximoError, match="invalid ACME account name"):
            _check_acme_account_name("a" * 65)


class TestCheckAcmePluginId:
    def test_valid_simple(self):
        assert _check_acme_plugin_id("dns-cf") == "dns-cf"

    def test_valid_with_underscore(self):
        assert _check_acme_plugin_id("my_plugin") == "my_plugin"

    def test_rejects_trailing_newline(self):
        with pytest.raises(ProximoError, match="invalid ACME plugin ID"):
            _check_acme_plugin_id("dns-cf\n")

    def test_rejects_slash(self):
        with pytest.raises(ProximoError, match="invalid ACME plugin ID"):
            _check_acme_plugin_id("bad/plugin")

    def test_rejects_empty(self):
        with pytest.raises(ProximoError, match="invalid ACME plugin ID"):
            _check_acme_plugin_id("")


# ---------------------------------------------------------------------------
# ACME account operations
# ---------------------------------------------------------------------------

class TestAcmeAccountGet:
    def test_calls_correct_path(self):
        api = _Api(get_returns={"/cluster/acme/account/default": {"name": "default"}})
        result = acme_account_get(api, "default")
        assert api.gets == ["/cluster/acme/account/default"]
        assert result["name"] == "default"

    def test_returns_empty_dict_on_none(self):
        api = _Api()
        assert acme_account_get(api, "missing") == {}

    def test_rejects_invalid_name(self):
        api = _Api()
        with pytest.raises(ProximoError, match="invalid ACME account name"):
            acme_account_get(api, "bad/name")


class TestAcmeAccountCreate:
    def test_posts_to_collection_with_name_in_body(self):
        """CREATE URL shape: POST /cluster/acme/account with name in body (Wave 1 lesson #2)."""
        api = _Api()
        acme_account_create(api, "default", "mailto:admin@example.com")
        assert api.posts == [(
            "/cluster/acme/account",
            {"name": "default", "contact": "mailto:admin@example.com"},
        )]

    def test_passes_optional_kwargs(self):
        api = _Api()
        acme_account_create(api, "prod", "admin@example.com", tos_url="https://example.com/tos")
        path, body = api.posts[0]
        assert path == "/cluster/acme/account"
        assert body["tos_url"] == "https://example.com/tos"

    def test_strips_none_kwargs(self):
        api = _Api()
        acme_account_create(api, "default", "admin@example.com", tos_url=None)
        path, body = api.posts[0]
        assert "tos_url" not in body

    def test_rejects_invalid_name(self):
        api = _Api()
        with pytest.raises(ProximoError, match="invalid ACME account name"):
            acme_account_create(api, "bad\nname", "admin@example.com")

    def test_no_get_calls(self):
        api = _Api()
        acme_account_create(api, "default", "admin@example.com")
        assert api.gets == []


class TestAcmeAccountUpdate:
    def test_puts_to_item_path(self):
        api = _Api()
        acme_account_update(api, "default", contact="newadmin@example.com")
        assert api.puts == [("/cluster/acme/account/default", {"contact": "newadmin@example.com"})]

    def test_strips_none_kwargs(self):
        api = _Api()
        acme_account_update(api, "default", contact=None, digest="abc123")
        path, body = api.puts[0]
        assert "contact" not in body
        assert body["digest"] == "abc123"

    def test_rejects_invalid_name(self):
        api = _Api()
        with pytest.raises(ProximoError, match="invalid ACME account name"):
            acme_account_update(api, "bad/name")


class TestAcmeAccountDelete:
    def test_deletes_item_path(self):
        api = _Api()
        acme_account_delete(api, "default")
        assert api.dels == ["/cluster/acme/account/default"]

    def test_no_other_side_effects(self):
        api = _Api()
        acme_account_delete(api, "default")
        assert api.gets == [] and api.posts == [] and api.puts == []

    def test_rejects_invalid_name(self):
        api = _Api()
        with pytest.raises(ProximoError, match="invalid ACME account name"):
            acme_account_delete(api, "bad\nname")


# ---------------------------------------------------------------------------
# ACME plugin operations
# ---------------------------------------------------------------------------

class TestAcmePluginGet:
    def test_calls_correct_path(self):
        api = _Api(get_returns={"/cluster/acme/plugins/dns-cf": {"id": "dns-cf"}})
        result = acme_plugin_get(api, "dns-cf")
        assert api.gets == ["/cluster/acme/plugins/dns-cf"]
        assert result["id"] == "dns-cf"

    def test_returns_empty_dict_on_none(self):
        api = _Api()
        assert acme_plugin_get(api, "missing") == {}

    def test_rejects_invalid_id(self):
        api = _Api()
        with pytest.raises(ProximoError, match="invalid ACME plugin ID"):
            acme_plugin_get(api, "bad/id")


class TestAcmePluginCreate:
    def test_posts_to_collection_with_id_in_body(self):
        """CREATE URL shape: POST /cluster/acme/plugins with id in body (Wave 1 lesson #2).

        Note: PVE ACME plugins have an 'api' body field (DNS provider name like 'cf', 'route53').
        The backend param is named 'backend', so the 'api' field rides safely inside **kw — see
        test_api_body_field_no_collision_with_backend below. This test uses 'data'.
        """
        api = _Api()
        acme_plugin_create(api, "dns-cf", "dns", data="CF_Token=abc")
        assert api.posts == [(
            "/cluster/acme/plugins",
            {"id": "dns-cf", "type": "dns", "data": "CF_Token=abc"},
        )]

    def test_strips_none_kwargs(self):
        api = _Api()
        acme_plugin_create(api, "my-plugin", "dns", data=None)
        path, body = api.posts[0]
        assert "data" not in body

    def test_rejects_invalid_id(self):
        api = _Api()
        with pytest.raises(ProximoError, match="invalid ACME plugin ID"):
            acme_plugin_create(api, "bad\nid", "dns")

    def test_no_get_calls(self):
        api = _Api()
        acme_plugin_create(api, "dns-cf", "dns")
        assert api.gets == []

    def test_api_body_field_no_collision_with_backend(self):
        # Regression: the DNS-provider 'api' body field must ride in **kw without colliding with
        # the backend positional param. This is the confirm=True executor path the golden sweep
        # can't reach (create's dry-run uses plan_acme_plugin_create, which has no backend param).
        api = _Api()
        acme_plugin_create(api, "dns-cf", "dns", **{"api": "cf", "data": "CF_Token=abc"})
        assert api.posts == [(
            "/cluster/acme/plugins",
            {"id": "dns-cf", "type": "dns", "api": "cf", "data": "CF_Token=abc"},
        )]


class TestAcmePluginUpdate:
    def test_puts_to_item_path(self):
        api = _Api()
        acme_plugin_update(api, "dns-cf", data="CF_Token=abc")
        assert api.puts == [("/cluster/acme/plugins/dns-cf", {"data": "CF_Token=abc"})]

    def test_strips_none_kwargs(self):
        api = _Api()
        acme_plugin_update(api, "dns-cf", data=None, disable=False)
        path, body = api.puts[0]
        assert "data" not in body

    def test_rejects_invalid_id(self):
        api = _Api()
        with pytest.raises(ProximoError, match="invalid ACME plugin ID"):
            acme_plugin_update(api, "bad/id")

    def test_api_body_field_no_collision_with_backend(self):
        # Regression: same dns_api↔backend collision on the update executor's confirm=True path.
        api = _Api()
        acme_plugin_update(api, "dns-cf", **{"api": "cf", "data": "CF_Token=abc"})
        assert api.puts == [("/cluster/acme/plugins/dns-cf", {"api": "cf", "data": "CF_Token=abc"})]


class TestAcmePluginDelete:
    def test_deletes_item_path(self):
        api = _Api()
        acme_plugin_delete(api, "dns-cf")
        assert api.dels == ["/cluster/acme/plugins/dns-cf"]

    def test_no_other_side_effects(self):
        api = _Api()
        acme_plugin_delete(api, "dns-cf")
        assert api.gets == [] and api.posts == [] and api.puts == []

    def test_rejects_invalid_id(self):
        api = _Api()
        with pytest.raises(ProximoError, match="invalid ACME plugin ID"):
            acme_plugin_delete(api, "bad\nid")


# ---------------------------------------------------------------------------
# Plan factory tests — ACME accounts
# ---------------------------------------------------------------------------

class TestPlanAcmeAccountCreate:
    def test_risk_is_medium(self):
        plan = plan_acme_account_create("default", "admin@example.com")
        assert plan.risk == RISK_MEDIUM

    def test_target_shape(self):
        plan = plan_acme_account_create("default", "admin@example.com")
        assert plan.target == "cluster/acme/account/default"

    def test_action_name(self):
        plan = plan_acme_account_create("default", "admin@example.com")
        assert plan.action == "pve_acme_account_create"

    def test_current_is_empty(self):
        plan = plan_acme_account_create("default", "admin@example.com")
        assert plan.current == {}

    def test_note_mentions_smoke_confirm(self):
        plan = plan_acme_account_create("default", "admin@example.com")
        assert "Smoke-confirm" in plan.note

    def test_rejects_invalid_name(self):
        with pytest.raises(ProximoError, match="invalid ACME account name"):
            plan_acme_account_create("bad/name", "admin@example.com")


class TestPlanAcmeAccountUpdate:
    def test_risk_is_low(self):
        """Account update is contact metadata only — no cert impact."""
        api = _Api(get_returns={"/cluster/acme/account/default": {"name": "default"}})
        plan = plan_acme_account_update(api, "default", contact="new@example.com")
        assert plan.risk == RISK_LOW

    def test_reads_current_config(self):
        api = _Api(get_returns={"/cluster/acme/account/default": {"name": "default", "contact": "old@example.com"}})
        plan = plan_acme_account_update(api, "default", contact="new@example.com")
        assert api.gets == ["/cluster/acme/account/default"]
        assert plan.current == {"name": "default", "contact": "old@example.com"}

    def test_blast_radius_says_no_cert_impact(self):
        api = _Api(get_returns={"/cluster/acme/account/default": {}})
        plan = plan_acme_account_update(api, "default")
        assert any("cert" in r.lower() or "contact" in r.lower() for r in plan.blast_radius)


class TestPlanAcmeAccountDelete:
    """The critical test: account delete must be HIGH + IRREVERSIBLE + TLS-lockout."""

    def test_risk_is_high(self):
        api = _Api(get_returns={"/cluster/acme/account/default": {"name": "default"}})
        plan = plan_acme_account_delete(api, "default")
        assert plan.risk == RISK_HIGH

    def test_reads_current_config_for_evidence(self):
        api = _Api(get_returns={"/cluster/acme/account/default": {"name": "default"}})
        plan = plan_acme_account_delete(api, "default")
        assert api.gets == ["/cluster/acme/account/default"]
        assert plan.current == {"name": "default"}

    def test_change_field_declares_irreversible(self):
        api = _Api(get_returns={"/cluster/acme/account/default": {}})
        plan = plan_acme_account_delete(api, "default")
        assert "IRREVERSIBLE" in plan.change

    def test_note_declares_irreversible(self):
        api = _Api(get_returns={"/cluster/acme/account/default": {}})
        plan = plan_acme_account_delete(api, "default")
        assert "IRREVERSIBLE" in plan.note

    def test_note_says_evidence_only_not_restore(self):
        api = _Api(get_returns={"/cluster/acme/account/default": {}})
        plan = plan_acme_account_delete(api, "default")
        assert "EVIDENCE ONLY" in plan.note
        assert "does NOT enable restore" in plan.note

    def test_blast_radius_mentions_tls_lockout(self):
        api = _Api(get_returns={"/cluster/acme/account/default": {}})
        plan = plan_acme_account_delete(api, "default")
        blast_text = " ".join(plan.blast_radius).lower()
        assert "tls lockout" in blast_text or "tls" in blast_text

    def test_blast_radius_mentions_renewal_stops(self):
        api = _Api(get_returns={"/cluster/acme/account/default": {}})
        plan = plan_acme_account_delete(api, "default")
        blast_text = " ".join(plan.blast_radius)
        assert "renew" in blast_text.lower() or "renewal" in blast_text.lower()

    def test_risk_reasons_say_irreversible(self):
        api = _Api(get_returns={"/cluster/acme/account/default": {}})
        plan = plan_acme_account_delete(api, "default")
        reasons_text = " ".join(plan.risk_reasons)
        assert "IRREVERSIBLE" in reasons_text

    def test_rejects_invalid_name(self):
        api = _Api()
        with pytest.raises(ProximoError, match="invalid ACME account name"):
            plan_acme_account_delete(api, "bad/name")


# ---------------------------------------------------------------------------
# Plan factory tests — ACME plugins
# ---------------------------------------------------------------------------

class TestPlanAcmePluginCreate:
    def test_risk_is_medium(self):
        plan = plan_acme_plugin_create("dns-cf", "dns")
        assert plan.risk == RISK_MEDIUM

    def test_target_shape(self):
        plan = plan_acme_plugin_create("dns-cf", "dns")
        assert plan.target == "cluster/acme/plugins/dns-cf"

    def test_action_name(self):
        plan = plan_acme_plugin_create("dns-cf", "dns")
        assert plan.action == "pve_acme_plugin_create"

    def test_current_is_empty(self):
        plan = plan_acme_plugin_create("dns-cf", "dns")
        assert plan.current == {}

    def test_note_mentions_smoke_confirm(self):
        plan = plan_acme_plugin_create("dns-cf", "dns")
        assert "Smoke-confirm" in plan.note

    def test_rejects_invalid_id(self):
        with pytest.raises(ProximoError, match="invalid ACME plugin ID"):
            plan_acme_plugin_create("bad/id", "dns")

    def test_redacts_data_credential_from_change(self):
        # `data` carries DNS-provider API credentials (e.g. CF_Token=...) — it must never land
        # in plan.change, which is both returned to the caller AND written to the PROVE ledger.
        plan = plan_acme_plugin_create("dns-cf", "dns", api="cf", data="CF_Token=SUPERSECRET")
        assert "CF_Token" not in plan.change
        assert "SUPERSECRET" not in plan.change
        assert "[redacted]" in plan.change
        assert "cf" in plan.change  # non-secret api field stays visible


class TestPlanAcmePluginUpdate:
    def test_risk_is_medium(self):
        api = _Api(get_returns={"/cluster/acme/plugins/dns-cf": {"id": "dns-cf"}})
        plan = plan_acme_plugin_update(api, "dns-cf", data="CF_Token=new")
        assert plan.risk == RISK_MEDIUM

    def test_reads_current_config(self):
        api = _Api(get_returns={"/cluster/acme/plugins/dns-cf": {"id": "dns-cf", "type": "dns"}})
        plan = plan_acme_plugin_update(api, "dns-cf", data="CF_Token=new")
        assert api.gets == ["/cluster/acme/plugins/dns-cf"]
        assert plan.current == {"id": "dns-cf", "type": "dns"}

    def test_redacts_data_credential_from_change(self):
        api = _Api(get_returns={"/cluster/acme/plugins/dns-cf": {"id": "dns-cf"}})
        plan = plan_acme_plugin_update(api, "dns-cf", data="CF_Token=SUPERSECRET")
        assert "CF_Token" not in plan.change
        assert "SUPERSECRET" not in plan.change
        assert "[redacted]" in plan.change

    def test_blast_radius_mentions_credentials(self):
        api = _Api(get_returns={"/cluster/acme/plugins/dns-cf": {}})
        plan = plan_acme_plugin_update(api, "dns-cf")
        blast_text = " ".join(plan.blast_radius).lower()
        assert "credential" in blast_text or "domain" in blast_text

    def test_redacts_data_credential_from_current(self):
        # acme_plugin_get's own documented shape includes `data` (the DNS provider's raw
        # API credential). plan.current is written verbatim to the PROVE ledger on every
        # call, dry-run included — the live credential must never land there.
        api = _Api(get_returns={
            "/cluster/acme/plugins/dns-cf": {"id": "dns-cf", "data": "CF_Token=LIVESECRET"},
        })
        plan = plan_acme_plugin_update(api, "dns-cf", api="cf")
        assert "LIVESECRET" not in str(plan.current)
        assert plan.current["data"] == "[redacted]"


class TestPlanAcmePluginDelete:
    """Plugin delete must be HIGH + renewal breaks + TLS-lockout blast_radius."""

    def test_risk_is_high(self):
        api = _Api(get_returns={"/cluster/acme/plugins/dns-cf": {"id": "dns-cf"}})
        plan = plan_acme_plugin_delete(api, "dns-cf")
        assert plan.risk == RISK_HIGH

    def test_reads_current_config_for_evidence(self):
        api = _Api(get_returns={"/cluster/acme/plugins/dns-cf": {"id": "dns-cf", "type": "dns"}})
        plan = plan_acme_plugin_delete(api, "dns-cf")
        assert api.gets == ["/cluster/acme/plugins/dns-cf"]
        assert plan.current == {"id": "dns-cf", "type": "dns"}

    def test_blast_radius_mentions_tls_lockout(self):
        api = _Api(get_returns={"/cluster/acme/plugins/dns-cf": {}})
        plan = plan_acme_plugin_delete(api, "dns-cf")
        blast_text = " ".join(plan.blast_radius).lower()
        assert "tls lockout" in blast_text or "tls" in blast_text

    def test_blast_radius_mentions_renewal_failure(self):
        api = _Api(get_returns={"/cluster/acme/plugins/dns-cf": {}})
        plan = plan_acme_plugin_delete(api, "dns-cf")
        blast_text = " ".join(plan.blast_radius).lower()
        assert "renewal" in blast_text or "renew" in blast_text

    def test_note_says_no_undo(self):
        api = _Api(get_returns={"/cluster/acme/plugins/dns-cf": {}})
        plan = plan_acme_plugin_delete(api, "dns-cf")
        assert "No UNDO primitive" in plan.note

    def test_note_says_credentials_not_returned(self):
        """Credentials must be re-supplied — stored secrets not returned by GET."""
        api = _Api(get_returns={"/cluster/acme/plugins/dns-cf": {}})
        plan = plan_acme_plugin_delete(api, "dns-cf")
        assert "credentials must be" in plan.note or "re-supplied" in plan.note

    def test_redacts_data_credential_from_current(self):
        # Same leak class as plan_acme_plugin_update: acme_plugin_get's documented shape
        # includes `data` — must never reach Plan.current (PROVE ledger + dry-run response).
        api = _Api(get_returns={
            "/cluster/acme/plugins/dns-cf": {"id": "dns-cf", "data": "CF_Token=LIVESECRET"},
        })
        plan = plan_acme_plugin_delete(api, "dns-cf")
        assert "LIVESECRET" not in str(plan.current)
        assert plan.current["data"] == "[redacted]"

    def test_risk_reasons_mention_autorenewal_breaks(self):
        api = _Api(get_returns={"/cluster/acme/plugins/dns-cf": {}})
        plan = plan_acme_plugin_delete(api, "dns-cf")
        reasons_text = " ".join(plan.risk_reasons).lower()
        assert "renewal" in reasons_text or "renew" in reasons_text

    def test_rejects_invalid_id(self):
        api = _Api()
        with pytest.raises(ProximoError, match="invalid ACME plugin ID"):
            plan_acme_plugin_delete(api, "bad/id")
