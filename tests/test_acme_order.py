"""Tests for the ACME cert-order plane (acme_certs.py additions).

Closes the ACME *order* gap: PVE could register an account + a DNS plugin via Proximo, but
nothing wired the node-side config (`acme=account=…`, `acmedomainN=domain=…,plugin=…`) nor the
order/renew/revoke endpoint (`/nodes/{node}/certificates/acme/certificate`). These tests pin:

  - _check_domain          : strict FQDN — the config-injection seam (`,`/`=`/space/non-ASCII all rejected)
  - _build_acme_node_config: account selector + per-domain plugin lines + REPLACE semantics
                             (stale acmedomainN indices are deleted, not left behind)
  - node_acme_config_set   : PUT /nodes/{node}/config body + delete shape
  - acme_cert_order/renew/revoke : correct verb (POST/PUT/DELETE), path, force handling
  - plan factories         : risk levels + honesty (order MEDIUM vs cert_upload HIGH; revoke HIGH/irreversible)
"""

from __future__ import annotations

import pytest

from proximo.acme_certs import (
    _build_acme_node_config,
    _check_domain,
    acme_cert_order,
    acme_cert_renew,
    acme_cert_revoke,
    node_acme_config_set,
    node_config_get,
    plan_acme_cert_order,
    plan_acme_cert_renew,
    plan_acme_cert_revoke,
    plan_node_acme_domains_set,
)
from proximo.backends import ProximoError
from proximo.planning import RISK_HIGH, RISK_MEDIUM


class _Api:
    """Recording fake: captures calls; _post/_put/_delete return a task UPID like a real order."""

    def __init__(self, get_returns: dict | None = None, task: str = "UPID:pve:0:0:order::root@pam:"):
        self.gets: list[str] = []
        self.posts: list[tuple[str, dict]] = []
        self.puts: list[tuple[str, dict]] = []
        self.dels: list[str] = []
        self._get_returns: dict = get_returns or {}
        self._task = task

    def _get(self, path: str):
        self.gets.append(path)
        return self._get_returns.get(path)

    def _post(self, path: str, data: dict | None = None):
        self.posts.append((path, data or {}))
        return self._task

    def _put(self, path: str, data: dict | None = None):
        self.puts.append((path, data or {}))
        return self._task

    def _delete(self, path: str):
        self.dels.append(path)
        return self._task


# ---------------------------------------------------------------------------
# _check_domain — the config-injection seam
# ---------------------------------------------------------------------------

class TestCheckDomain:
    def test_valid_fqdn(self):
        assert _check_domain("node.example.com") == "node.example.com"

    def test_valid_multi_label(self):
        assert _check_domain("a.b.c.example.co") == "a.b.c.example.co"

    def test_rejects_trailing_newline(self):
        # \Z (not $) — a trailing newline must not slip a second config line through.
        with pytest.raises(ProximoError):
            _check_domain("node.example.com\n")

    def test_rejects_comma(self):
        # comma is PVE's config-property delimiter — injection of ,plugin=evil must be impossible.
        with pytest.raises(ProximoError):
            _check_domain("node.example.com,plugin=evil")

    def test_rejects_equals(self):
        with pytest.raises(ProximoError):
            _check_domain("a=b.com")

    def test_rejects_whitespace(self):
        with pytest.raises(ProximoError):
            _check_domain("pve .com")

    def test_rejects_non_ascii(self):
        # must be pre-punycoded — raw IDN rejected.
        with pytest.raises(ProximoError):
            _check_domain("café.com")

    def test_rejects_empty(self):
        with pytest.raises(ProximoError):
            _check_domain("")

    def test_rejects_single_label(self):
        # a public ACME cert needs a dotted FQDN, not a bare hostname.
        with pytest.raises(ProximoError):
            _check_domain("pve")

    def test_rejects_leading_hyphen_label(self):
        with pytest.raises(ProximoError):
            _check_domain("-bad.com")

    def test_rejects_label_too_long(self):
        with pytest.raises(ProximoError):
            _check_domain("a" * 64 + ".com")

    def test_rejects_total_too_long(self):
        with pytest.raises(ProximoError):
            _check_domain((("a" * 60 + ".") * 5) + "com")


# ---------------------------------------------------------------------------
# _build_acme_node_config — account selector, plugin lines, REPLACE semantics
# ---------------------------------------------------------------------------

class TestBuildAcmeNodeConfig:
    def test_dns01_single_domain_sets_account_and_acmedomain0(self):
        body, delete = _build_acme_node_config(
            account="le", domains=["node.example.com"], plugin="technitium", current={}
        )
        assert body["acme"] == "account=le"
        assert body["acmedomain0"] == "domain=node.example.com,plugin=technitium"
        assert delete is None

    def test_dns01_multi_domain_indexes_each(self):
        body, _ = _build_acme_node_config(
            account="le", domains=["a.example.com", "b.example.com"], plugin="tech", current={}
        )
        assert body["acmedomain0"] == "domain=a.example.com,plugin=tech"
        assert body["acmedomain1"] == "domain=b.example.com,plugin=tech"

    def test_standalone_no_plugin_uses_acme_domains_list(self):
        # No plugin → http-01 standalone: domains ride in `acme=...,domains=d;d`, no acmedomainN.
        body, _ = _build_acme_node_config(
            account="le", domains=["a.example.com", "b.example.com"], plugin=None, current={}
        )
        assert body["acme"] == "account=le,domains=a.example.com;b.example.com"
        assert not any(k.startswith("acmedomain") for k in body)

    def test_replace_deletes_stale_acmedomain_indices(self):
        # current has 0,1,2 set; new list has 1 → indices 1,2 are stale and must be deleted.
        current = {
            "acme": "account=old",
            "acmedomain0": "domain=x.example.com,plugin=p",
            "acmedomain1": "domain=y.example.com,plugin=p",
            "acmedomain2": "domain=z.example.com,plugin=p",
        }
        body, delete = _build_acme_node_config(
            account="le", domains=["new.example.com"], plugin="p", current=current
        )
        assert body["acmedomain0"] == "domain=new.example.com,plugin=p"
        assert delete == "acmedomain1,acmedomain2"

    def test_standalone_deletes_all_prior_acmedomain_indices(self):
        current = {"acmedomain0": "domain=x.example.com,plugin=p"}
        _, delete = _build_acme_node_config(
            account="le", domains=["a.example.com"], plugin=None, current=current
        )
        assert delete == "acmedomain0"

    def test_rejects_more_than_six_domains(self):
        with pytest.raises(ProximoError):
            _build_acme_node_config(
                account="le",
                domains=[f"d{i}.example.com" for i in range(7)],
                plugin="p",
                current={},
            )

    def test_rejects_empty_domains(self):
        with pytest.raises(ProximoError):
            _build_acme_node_config(account="le", domains=[], plugin="p", current={})

    def test_validates_every_domain(self):
        with pytest.raises(ProximoError):
            _build_acme_node_config(
                account="le", domains=["ok.example.com", "bad,inject=x"], plugin="p", current={}
            )

    def test_rejects_invalid_account(self):
        with pytest.raises(ProximoError):
            _build_acme_node_config(account="bad/acct", domains=["a.example.com"], plugin="p", current={})

    def test_rejects_invalid_plugin(self):
        with pytest.raises(ProximoError):
            _build_acme_node_config(account="le", domains=["a.example.com"], plugin="bad/plug", current={})


# ---------------------------------------------------------------------------
# node_config_get / node_acme_config_set — read + PUT shapes
# ---------------------------------------------------------------------------

class TestNodeConfig:
    def test_get_calls_node_config_path(self):
        api = _Api(get_returns={"/nodes/pve/config": {"acme": "account=le"}})
        assert node_config_get(api, "pve") == {"acme": "account=le"}
        assert api.gets == ["/nodes/pve/config"]

    def test_get_rejects_invalid_node(self):
        with pytest.raises(ProximoError):
            node_config_get(_Api(), "bad/node")

    def test_set_puts_config_with_acme_and_acmedomain(self):
        api = _Api(get_returns={"/nodes/pve/config": {}})
        node_acme_config_set(api, "pve", account="le", domains=["node.example.com"], plugin="technitium")
        assert len(api.puts) == 1
        path, body = api.puts[0]
        assert path == "/nodes/pve/config"
        assert body["acme"] == "account=le"
        assert body["acmedomain0"] == "domain=node.example.com,plugin=technitium"

    def test_set_includes_delete_for_stale_indices(self):
        api = _Api(get_returns={"/nodes/pve/config": {"acmedomain0": "domain=a.com,plugin=p",
                                                       "acmedomain1": "domain=b.example.com,plugin=p"}})
        node_acme_config_set(api, "pve", account="le", domains=["only.example.com"], plugin="p")
        _, body = api.puts[0]
        assert body.get("delete") == "acmedomain1"

    def test_set_rejects_invalid_node(self):
        with pytest.raises(ProximoError):
            node_acme_config_set(_Api(), "bad/node", account="le",
                                 domains=["a.example.com"], plugin="p")


# ---------------------------------------------------------------------------
# Order / renew / revoke ops — verb, path, force
# ---------------------------------------------------------------------------

_CERT_PATH = "/nodes/pve/certificates/acme/certificate"


class TestCertOrderOps:
    def test_order_posts_to_cert_path(self):
        api = _Api()
        upid = acme_cert_order(api, "pve")
        assert api.posts == [(_CERT_PATH, {})]
        assert upid == api._task

    def test_order_force_sends_force_1(self):
        api = _Api()
        acme_cert_order(api, "pve", force=True)
        assert api.posts == [(_CERT_PATH, {"force": 1})]

    def test_renew_puts_to_cert_path(self):
        api = _Api()
        acme_cert_renew(api, "pve")
        assert api.puts == [(_CERT_PATH, {})]

    def test_renew_force_sends_force_1(self):
        api = _Api()
        acme_cert_renew(api, "pve", force=True)
        assert api.puts == [(_CERT_PATH, {"force": 1})]

    def test_revoke_deletes_cert_path(self):
        api = _Api()
        acme_cert_revoke(api, "pve")
        assert api.dels == [_CERT_PATH]

    def test_order_rejects_invalid_node(self):
        with pytest.raises(ProximoError):
            acme_cert_order(_Api(), "bad/node")

    def test_revoke_rejects_invalid_node(self):
        with pytest.raises(ProximoError):
            acme_cert_revoke(_Api(), "bad/node")


# ---------------------------------------------------------------------------
# Plan factories — risk story
# ---------------------------------------------------------------------------

class TestPlanFactories:
    def test_domains_set_is_medium_and_captures_current(self):
        api = _Api(get_returns={"/nodes/pve/config": {"acme": "account=old"}})
        plan = plan_node_acme_domains_set(api, "pve", account="le",
                                          domains=["node.example.com"], plugin="technitium")
        assert plan.risk == RISK_MEDIUM
        assert plan.current == {"acme": "account=old"}  # honesty: prior config captured for revert

    def test_order_is_medium_not_high(self):
        # Asymmetry vs pve_node_cert_upload (HIGH): an ACME order is CA-validated and PVE installs
        # only on success — a failed challenge leaves the existing cert untouched.
        plan = plan_acme_cert_order("pve")
        assert plan.risk == RISK_MEDIUM

    def test_order_blast_mentions_install_on_success_and_revert(self):
        plan = plan_acme_cert_order("pve")
        blob = (" ".join(plan.blast_radius) + " " + plan.note).lower()
        assert "pve_node_cert_delete" in blob  # the documented revert path
        assert "success" in blob                # installs only on success

    def test_renew_is_medium(self):
        assert plan_acme_cert_renew("pve").risk == RISK_MEDIUM

    def test_revoke_is_high_and_irreversible(self):
        plan = plan_acme_cert_revoke(_Api(), "pve")
        assert plan.risk == RISK_HIGH
        assert "irreversible" in (plan.change + plan.note).lower()

    def test_order_rejects_invalid_node(self):
        with pytest.raises(ProximoError):
            plan_acme_cert_order("bad/node")


# ---------------------------------------------------------------------------
# Review findings (adversarial review 2026-06-29)
# ---------------------------------------------------------------------------

class TestReviewFindings:
    # F1 — wildcard ACME certs (DNS-01) must be accepted, without opening an injection seam.
    def test_wildcard_domain_accepted(self):
        assert _check_domain("*.example.com") == "*.example.com"

    def test_wildcard_still_rejects_property_injection(self):
        with pytest.raises(ProximoError):
            _check_domain("*.example.com,plugin=evil")

    def test_bare_star_or_mid_label_star_rejected(self):
        for bad in ("*example.com", "*.*.example.com", "a.*.example.com"):
            with pytest.raises(ProximoError):
                _check_domain(bad)

    def test_wildcard_with_plugin_builds_acmedomain(self):
        body, _ = _build_acme_node_config(
            account="le", domains=["*.example.com"], plugin="tech", current={}
        )
        assert body["acmedomain0"] == "domain=*.example.com,plugin=tech"

    def test_wildcard_without_plugin_rejected(self):
        # LE cannot validate a wildcard via http-01 standalone — DNS-01 plugin is mandatory.
        with pytest.raises(ProximoError):
            _build_acme_node_config(account="le", domains=["*.example.com"], plugin=None, current={})

    # F2 — an out-of-range acmedomainN (>5) in current must NOT be emitted in delete= (PVE 400s).
    def test_out_of_range_acmedomain_index_not_deleted(self):
        current = {"acmedomain0": "domain=a.example.com,plugin=p",
                   "acmedomain6": "domain=stray.example.com,plugin=p"}
        _, delete = _build_acme_node_config(
            account="le", domains=["new.example.com"], plugin="p", current=current
        )
        # only valid 0..5 indices participate; acmedomain6 is ignored, acmedomain0 is reused.
        assert delete is None

    # F3 — a HIGH/irreversible revoke must capture cert evidence into the PROVE ledger.
    def test_revoke_plan_captures_cert_evidence(self):
        api = _Api(get_returns={
            "/nodes/pve/certificates": [{"fingerprint": "AA:BB", "subject": "CN=pve"}]
        })
        plan = plan_acme_cert_revoke(api, "pve")
        assert plan.current  # not empty — evidence of what is being destroyed
        assert "AA:BB" in str(plan.current)
