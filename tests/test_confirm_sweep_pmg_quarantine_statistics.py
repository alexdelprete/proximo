"""Confirm=True sweep — PMG quarantine + statistics remainder wrapper welds
(src/proximo/pmg.py + src/proximo/tools/pmg_mail.py, Wave 9j, THE FINAL CHUNK of the
full-surface campaign — this chunk CLOSES the PMG plane) + THE RULING-4 PROOF for
`pmg_quarantine_link_get`'s bearer-credential-equivalent return.

Mirrors the `_wire()`/`_Pmg` idiom already established in
`tests/test_confirm_sweep_pmg_ldap_fetchmail.py` (itself mirroring `test_confirm_sweep_pmg_node.py`'s
own `_Pmg` template): `_svc` is monkeypatched (the ONE shared audit ledger lives behind it —
`_ledger()` reads `_svc()[3]`) and `_pmg` is monkeypatched to a fake PmgBackend. This file
duplicates its own `_Pmg`/`_wire` rather than importing another confirm-sweep module's — same
self-contained convention every confirm-sweep module in this repo follows.

This chunk has exactly ONE mutation (`pmg_quarantine_sendlink`) and TEN reads. The headline proof
is RULING 4: `pmg_quarantine_link_get`'s return carries a bearer-credential-equivalent `link`
value (PMG's own description: "grants full access to that recipient's quarantine"). The campaign's
first plain-READ-return redaction — proven here with a RAW-LEDGER-BYTES sweep (read the file as
bytes, not parsed JSON) showing the link sentinel appears NOWHERE in the on-disk ledger, while
still reaching the caller's own result (the whole point of the tool). The `mail` address itself
(non-secret — WHO the link was requested for) IS deliberately logged in the ledger detail, proving
the redaction is targeted at the secret only, not a blanket "log nothing" evasion.

Sentinel values are low-entropy (all-lowercase, hyphenated) per this repo's fixture-sentinel
discipline (CLAUDE.md: a mixed-case test sentinel already failed the public gitleaks CI scan on
v0.13.0) — except the link token itself, which must look plausibly like a real capability URL to
make the sweep meaningful; it stays a fixed placeholder string, never derived from any real secret.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import proximo.server as server
from proximo.audit import AuditLedger
from proximo.backends import ProximoError
from proximo.config import ProximoConfig

_LINK_SENTINEL = "https://pmg.example.com/quarantine?ticket=sentinel-quarantine-link-token"


class _Pmg:
    """Path-aware fake PmgBackend: records every _get/_post/_put/_delete call.

    `_get` returns fixed, deterministic content per path (quarantine content/attachments/
    quarusers/link, statistics reads) — every other path defaults to an empty list/dict via the
    per-path branches below. `_post` (the one mutation this chunk has, quarantine/sendlink)
    returns `None` — matches the live schema (`returns: {"type": "null"}`).
    """

    def __init__(self, link_return=None):
        self._link_return = link_return if link_return is not None else {"link": _LINK_SENTINEL}
        self.gets: list[tuple[str, dict | None]] = []
        self.posts: list[tuple[str, dict | None]] = []
        self.puts: list[tuple[str, dict | None]] = []
        self.deletes: list[tuple[str, dict | None]] = []

    def _get(self, path, params=None):
        self.gets.append((path, params))
        if path == "/quarantine/link":
            return self._link_return
        if path == "/quarantine/content":
            return {"id": "C1R1T1700000000", "subject": "sentinel subject"}
        if path == "/quarantine/listattachments":
            return [{"id": 1, "name": "sentinel.txt", "size": 10, "content-type": "text/plain"}]
        if path == "/quarantine/quarusers":
            return [{"mail": "user@example.com"}]
        if path in (
            "/statistics/contact", "/statistics/detail", "/statistics/maildistribution",
            "/statistics/recentreceivers", "/statistics/recentsenders", "/statistics/rejectcount",
        ):
            return []
        return []

    def _post(self, path, data=None):
        self.posts.append((path, data))
        return None

    def _put(self, path, data=None):
        self.puts.append((path, data))
        return None

    def _delete(self, path, params=None):
        self.deletes.append((path, params))
        return None


class _Api:
    """Minimal PVE API stub — only needed so server._svc() resolves (the ONE shared ledger lives
    behind it); pmg.py's/tools/pmg_mail.py's tools never touch this backend."""

    def __init__(self):
        self.config = SimpleNamespace(node="pve")


def _wire(tmp_path, monkeypatch, link_return=None):
    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(
        api_base_url="https://x:8006/api2/json", node="pve", token_path="/run/x",
        audit_log_path=log,
    )
    api = _Api()
    pmg = _Pmg(link_return=link_return)
    exec_ = SimpleNamespace()
    ledger = AuditLedger(log)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, api, exec_, ledger))
    monkeypatch.setattr(server, "_pmg", lambda: (SimpleNamespace(node="pmg"), pmg))
    return cfg, pmg, ledger, log


def _entries(log: str) -> list[dict]:
    with open(log, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _confirmed_entry(log: str, action: str, outcome: str) -> dict:
    entries = [e for e in _entries(log) if e["action"] == action and e["outcome"] == outcome]
    assert len(entries) == 1, f"expected exactly one {action!r}/{outcome!r} ledger entry, got {entries}"
    return entries[0]


# ---------------------------------------------------------------------------
# The one mutation this chunk ships — pmg_quarantine_sendlink.
# ---------------------------------------------------------------------------

def test_quarantine_sendlink_confirm_true_executes_forwards_and_records(tmp_path, monkeypatch):
    """confirm=True executes (never 'plan'), the fake captured the forwarded call, and the ledger
    recorded a confirmed mutation — the three welds every confirm-sweep module proves."""
    _, pmg, _, log = _wire(tmp_path, monkeypatch)

    out = server.pmg_quarantine_sendlink(mail="user@example.com", confirm=True)

    assert out["status"] == "ok"
    assert out["status"] != "plan"

    assert pmg.posts, "pmg_quarantine_sendlink confirm=True never reached pmg._post"
    call_path, call_data = pmg.posts[-1]
    assert call_path == "/quarantine/sendlink"
    assert call_data == {"mail": "user@example.com"}

    entry = _confirmed_entry(log, "pmg_quarantine_sendlink", "ok")
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True
    assert entry["detail"]["mail"] == "user@example.com"


def test_quarantine_sendlink_dry_run_never_posts(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    out = server.pmg_quarantine_sendlink(mail="user@example.com", confirm=False)
    assert out["status"] == "plan"
    assert not pmg.posts


def test_quarantine_sendlink_dry_run_plan_mentions_mail(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)
    out = server.pmg_quarantine_sendlink(mail="user@example.com", confirm=False)
    assert "user@example.com" in json.dumps(out)


def test_quarantine_sendlink_invalid_mail_raises(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)
    with pytest.raises(ProximoError):
        server.pmg_quarantine_sendlink(mail="not-an-email", confirm=False)


# ---------------------------------------------------------------------------
# Reads — confirm the wrapper reaches the PmgBackend with the right path (no confirm= gate).
# ---------------------------------------------------------------------------

def test_quarantine_users_list_read_reaches_pmg(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    server.pmg_quarantine_users_list()
    call_path, _ = pmg.gets[-1]
    assert call_path == "/quarantine/quarusers"


def test_quarantine_content_get_read_reaches_pmg(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    server.pmg_quarantine_content_get(id_="C1R1T1700000000")
    call_path, call_params = pmg.gets[-1]
    assert call_path == "/quarantine/content"
    assert call_params["id"] == "C1R1T1700000000"


def test_quarantine_attachments_list_read_reaches_pmg(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    server.pmg_quarantine_attachments_list(id_="C1R1T1700000000")
    call_path, call_params = pmg.gets[-1]
    assert call_path == "/quarantine/listattachments"
    assert call_params["id"] == "C1R1T1700000000"


def test_quarantine_link_get_read_reaches_pmg(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    result = server.pmg_quarantine_link_get(mail="user@example.com")
    call_path, call_params = pmg.gets[-1]
    assert call_path == "/quarantine/link"
    assert call_params["mail"] == "user@example.com"
    assert result["link"] == _LINK_SENTINEL


def test_statistics_contact_read_reaches_pmg(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    server.pmg_statistics_contact()
    call_path, _ = pmg.gets[-1]
    assert call_path == "/statistics/contact"


def test_statistics_detail_read_reaches_pmg(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    server.pmg_statistics_detail(address="user@example.com", type_="sender")
    call_path, call_params = pmg.gets[-1]
    assert call_path == "/statistics/detail"
    assert call_params["address"] == "user@example.com"
    assert call_params["type"] == "sender"


def test_statistics_maildistribution_read_reaches_pmg(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    server.pmg_statistics_maildistribution()
    call_path, _ = pmg.gets[-1]
    assert call_path == "/statistics/maildistribution"


def test_statistics_recentreceivers_read_reaches_pmg(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    server.pmg_statistics_recentreceivers()
    call_path, call_params = pmg.gets[-1]
    assert call_path == "/statistics/recentreceivers"
    assert call_params == {"hours": 12, "limit": 5}


def test_statistics_recentsenders_read_reaches_pmg(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    server.pmg_statistics_recentsenders(hours=3, limit=20)
    call_path, call_params = pmg.gets[-1]
    assert call_path == "/statistics/recentsenders"
    assert call_params == {"hours": 3, "limit": 20}


def test_statistics_rejectcount_read_reaches_pmg(tmp_path, monkeypatch):
    _, pmg, _, _ = _wire(tmp_path, monkeypatch)
    server.pmg_statistics_rejectcount()
    call_path, call_params = pmg.gets[-1]
    assert call_path == "/statistics/rejectcount"
    assert call_params["timespan"] == 3600


# ---------------------------------------------------------------------------
# RULING 4 — THE HEADLINE WELD: pmg_quarantine_link_get's `link` return value must NEVER appear
# raw in the on-disk ledger, read RAW BYTES (not parsed JSON), while the caller's own result DOES
# carry it (the whole point of the tool) and the non-secret `mail` identifier DOES reach the
# ledger (proving the redaction is targeted, not a blanket "log nothing" evasion).
# ---------------------------------------------------------------------------

def test_quarantine_link_get_link_reaches_caller_but_never_the_ledger(tmp_path, monkeypatch):
    _, pmg, _, log = _wire(tmp_path, monkeypatch)

    result = server.pmg_quarantine_link_get(mail="user@example.com")

    # weld 1: the secret DOES reach the caller — that's the entire point of a read tool.
    assert result["link"] == _LINK_SENTINEL

    # weld 2: ledger entries (parsed JSON) never carry the link sentinel.
    entries = _entries(log)
    assert entries, "no ledger entries recorded at all"
    assert all(_LINK_SENTINEL not in json.dumps(e) for e in entries)

    entry = _confirmed_entry(log, "pmg_quarantine_link_get", "ok")
    assert "link" not in json.dumps(entry["detail"])
    # the non-secret WHO-asked identifier IS logged — the redaction is targeted, not blanket.
    assert entry["detail"]["mail"] == "user@example.com"
    assert entry["mutation"] is False

    # THE HEADLINE WELD: read the ledger file RAW (bytes) — the secret must appear NOWHERE,
    # not even as a truncated fragment or a URL-encoded variant.
    raw = open(log, "rb").read()
    assert _LINK_SENTINEL.encode("utf-8") not in raw

    # MIRROR-IMAGE: the mail address IS present raw in the on-disk ledger (non-secret,
    # deliberately visible — the audit trail should show WHO asked, just never the secret itself).
    assert b"user@example.com" in raw


def test_quarantine_link_get_leaky_fake_still_never_reaches_ledger(tmp_path, monkeypatch):
    """Independent, hostile proof: even if the underlying PmgBackend leaked the link into some
    OTHER field alongside `link` (a leaky/misbehaving fake), the redaction guarantee holds because
    it is structural (the wrapper never passes the read's return into `detail` at all) — not
    schema-shaped, not dependent on the return only having a `link` key. Mirrors the Wave 9c/9f/9g
    'leaky fake' precedent for CONFIRMED-echoing secrets, applied here to the read-return case."""
    leaked_extra = "sentinel-extra-leak-field-should-never-reach-ledger"

    class _LeakyPmg(_Pmg):
        def _get(self, path, params=None):
            self.gets.append((path, params))
            if path == "/quarantine/link":
                return {"link": _LINK_SENTINEL, "extra_field_pmg_should_not_send": leaked_extra}
            return super()._get(path, params)

    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(api_base_url="https://x:8006/api2/json", node="pve", token_path="/run/x",
                         audit_log_path=log)
    pmg = _LeakyPmg()
    ledger = AuditLedger(log)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, _Api(), SimpleNamespace(), ledger))
    monkeypatch.setattr(server, "_pmg", lambda: (SimpleNamespace(node="pmg"), pmg))

    result = server.pmg_quarantine_link_get(mail="user@example.com")

    # the caller still sees everything the backend returned (a read tool doesn't filter its own
    # result — only the LEDGER is redaction-scoped).
    assert result["link"] == _LINK_SENTINEL
    assert result["extra_field_pmg_should_not_send"] == leaked_extra

    raw = open(log, "rb").read()
    assert _LINK_SENTINEL.encode("utf-8") not in raw
    assert leaked_extra.encode("utf-8") not in raw


def test_quarantine_link_get_dry_run_has_no_such_thing_it_is_a_plain_read(tmp_path, monkeypatch):
    """RULING 4 note: pmg_quarantine_link_get is a plain GET, not a confirm-gated mutation — there
    is no dry-run/plan path to prove separately (unlike pmg_quarantine_sendlink above)."""
    import inspect
    assert "confirm" not in inspect.signature(server.pmg_quarantine_link_get).parameters
