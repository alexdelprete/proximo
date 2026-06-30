"""Proximo PMG (Proxmox Mail Gateway) lane — backend + tool/plan surface.

Separate backend because PMG is a distinct service from the PVE host:
- API base: https://<pmg-host>:8006/api2/json  (same port as PVE, different host)
- Auth:     ticket-based — CONFIRMED against PMG 9.1:
              POST /access/ticket → {ticket, CSRFPreventionToken}
              Cookie: PMGAuthCookie=<ticket>  (all authenticated requests)
              CSRFPreventionToken: <token>     (mutations only — POST/PUT/DELETE)
            No API tokens in PMG (the only APIToken code in PMG is its PBS-client).
- Paths:    /nodes/{node}/...  /config/...  /statistics/...  /quarantine/...

Most endpoint paths and response shapes are "PMG 9.1 live-verified" via the W1–W5 PMG live-smoke
(auth, read shapes, CRUD cycles, service restart, RuleDB paths). Remaining "Smoke-confirm:" notes
flag specific response field names or edge-case constraints that are not yet confirmed by live-smoke.

Security posture mirrors pbs.py (and is stricter on TLS):
- Password read at login time from password_path; NEVER logged or cached on disk.
- Ticket + CSRF cached in memory only; cleared on 401 and refreshed by a single re-login.
- TLS verification prefers ca_bundle over disabling. FAIL-CLOSED: constructing a
  PmgBackend with verify_tls=False AND no ca_bundle raises — the credential-bearing
  backend refuses to send credentials over a completely unverified channel.
- Input validators use \\Z (not $) to block trailing-newline bypass.
"""

from __future__ import annotations

import ipaddress
import os
import re
import threading
import warnings
from dataclasses import dataclass
from urllib.parse import quote

import httpx

from ._tls import httpx_verify, parse_verify_tls
from .backends import ProximoError
from .planning import RISK_HIGH, RISK_LOW, RISK_MEDIUM, Plan

# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

# Node name: Proxmox node names are alphanumeric + hyphen; no slash or control chars.
# Smoke-confirm: exact accepted charset for PMG node names (may differ from PVE).
_NODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,63}\Z")

# Quarantine mail ID: used as a URL path segment — reject traversal, control chars,
# slash, and semicolons. Exact format is PMG-version-specific.
# Smoke-confirm: exact format of PMG quarantine mail IDs.
_MAIL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")


def _check_node(node: str) -> str:
    # Do NOT strip — stripping defeats \Z trailing-newline protection.
    s = str(node)
    if not _NODE_RE.match(s):
        raise ProximoError(
            f"invalid PMG node name: {node!r} "
            "(must start with alnum, then alnum/hyphen, <=64 chars, no control chars)"
        )
    return s


def _check_mail_id(mail_id: str) -> str:
    # Do NOT strip — \Z must catch trailing newlines.
    s = str(mail_id)
    if not _MAIL_ID_RE.match(s):
        raise ProximoError(
            f"invalid quarantine mail ID: {mail_id!r} "
            "(start with alnum, then alnum/._/-, <=128 chars, no slash or control chars)"
        )
    return s


# Tracker IDs are used as a URL path segment in /nodes/{node}/tracker/{id}. They are mail/queue-ish
# tokens (alnum plus a few mail chars); a slash, '..', or query/fragment metachar would be path
# traversal or request injection. We allow a permissive mail charset but reject the structural chars.
_TRACKER_ID_BAD = ("/", "\\", "?", "#", "%", "\x00", "\r", "\n", "\t", " ")


def _check_tracker_id(tracker_id: str) -> str:
    s = str(tracker_id)
    if not s or ".." in s or any(c in s for c in _TRACKER_ID_BAD):
        raise ProximoError(
            f"invalid tracker id: {tracker_id!r} "
            "(no '/', '\\', '..', '?', '#', '%', whitespace or control chars — path-segment safe)"
        )
    return s


# Service name: PMG service names are alphanumeric + hyphen (e.g. pmg-smtp-filter, spamassassin).
# Same charset as node names — protects against path traversal when used as a URL segment.
_SERVICE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,63}\Z")


def _check_service(service: str) -> str:
    # Do NOT strip — \Z must catch trailing newlines.
    s = str(service)
    if not _SERVICE_RE.match(s):
        raise ProximoError(
            f"invalid PMG service name: {service!r} "
            "(must start with alnum, then alnum/hyphen, <=64 chars, no control chars)"
        )
    return s


# Valid quarantine action values (pmgsh ls-verified path: POST /quarantine/content).
_QUARANTINE_ACTIONS = frozenset({
    "deliver", "delete", "mark-seen", "mark-unseen", "blocklist", "welcomelist",
})


# ---------------------------------------------------------------------------
# W3 Validators
# ---------------------------------------------------------------------------

# Domain name: used as URL path segment — reject traversal (slashes, ..), control chars.
# Allows alphanumeric, dots, hyphens, underscores (standard DNS charset including underscore
# labels like _dmarc.example.com). Leading hyphen is still rejected (starts with alnum or _).
_DOMAIN_RE = re.compile(r"^[A-Za-z0-9_]([A-Za-z0-9._-]*[A-Za-z0-9_])?\Z")


def _check_domain(domain: str) -> str:
    # Do NOT strip — \Z must catch trailing newlines.
    s = str(domain)
    if not _DOMAIN_RE.match(s):
        raise ProximoError(
            f"invalid domain: {domain!r} "
            "(must start with alnum, allow alnum/dots/hyphens/underscores, "
            "no slash or control chars)"
        )
    return s


def _check_cidr(cidr: str) -> str:
    """Validate a CIDR network expression using the stdlib ipaddress module.

    Uses strict=False so host bits are tolerated (e.g. '192.168.1.1/24'
    is accepted as '192.168.1.0/24'). Trailing whitespace and newlines
    cause ValueError in the stdlib parser and are therefore rejected.
    """
    try:
        ipaddress.ip_network(str(cidr), strict=False)
    except ValueError as exc:
        raise ProximoError(
            f"invalid CIDR: {cidr!r} — {exc}"
        ) from exc
    return str(cidr)


# Transport protocol: PMG 9.1 live-verified via pmgsh help /config/transport.
_TRANSPORT_PROTOCOLS = frozenset({"smtp", "lmtp"})


def _check_transport_protocol(protocol: str) -> str:
    if protocol not in _TRANSPORT_PROTOCOLS:
        raise ProximoError(
            f"invalid transport protocol: {protocol!r}. "
            f"Must be one of: {', '.join(sorted(_TRANSPORT_PROTOCOLS))}"
        )
    return protocol


# Service action: valid actions for /nodes/{node}/services/{service}/{action}.
# PMG 9.1 live-verified via pmgsh ls.
_SERVICE_ACTIONS = frozenset({"start", "stop", "restart", "reload"})


def _check_service_action(action: str) -> str:
    if action not in _SERVICE_ACTIONS:
        raise ProximoError(
            f"invalid service action: {action!r}. "
            f"Must be one of: {', '.join(sorted(_SERVICE_ACTIONS))}"
        )
    return action


# ---------------------------------------------------------------------------
# PmgConfig
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PmgConfig:
    """Configuration for the PMG API backend.

    All credentials are referenced by PATH — values are read at call time
    and never logged, so the secrets vault is never echoed.

    env vars:
        PROXIMO_PMG_BASE_URL       required  https://<host>:8006/api2/json
        PROXIMO_PMG_PASSWORD_PATH  required  file containing the PMG user password
        PROXIMO_PMG_USERNAME       optional  default "root@pam"
        PROXIMO_PMG_NODE           optional  default "pmg"
        PROXIMO_PMG_VERIFY_TLS     optional  default "true"; set "false" to skip (warn)
        PROXIMO_PMG_CA_BUNDLE      optional  path to CA cert bundle (preferred over disabling TLS)
    """

    base_url: str        # e.g. "https://pmg.example.lan:8006/api2/json"
    password_path: str   # file containing the PMG user password (read at login time)
    username: str = "root@pam"
    node: str = "pmg"
    verify_tls: bool = True
    ca_bundle: str | None = None

    @classmethod
    def from_env(cls) -> PmgConfig:
        try:
            base_url = os.environ["PROXIMO_PMG_BASE_URL"]
            password_path = os.environ["PROXIMO_PMG_PASSWORD_PATH"]
        except KeyError as e:
            raise RuntimeError(
                f"Missing required PMG env var: {e.args[0]}. "
                "Set PROXIMO_PMG_BASE_URL and PROXIMO_PMG_PASSWORD_PATH to configure "
                "the Proxmox Mail Gateway backend."
            ) from e

        username = os.environ.get("PROXIMO_PMG_USERNAME", "root@pam")
        node = os.environ.get("PROXIMO_PMG_NODE", "pmg")
        verify_tls = parse_verify_tls(os.environ.get("PROXIMO_PMG_VERIFY_TLS", "true"))
        ca_bundle = os.environ.get("PROXIMO_PMG_CA_BUNDLE") or None

        if not verify_tls and not ca_bundle:
            warnings.warn(
                "PROXIMO_PMG_VERIFY_TLS=false with no CA bundle — "
                "talking to the PMG API without cert validation.",
                stacklevel=2,
            )

        return cls(
            base_url=base_url.rstrip("/"),
            password_path=password_path,
            username=username,
            node=node,
            verify_tls=verify_tls,
            ca_bundle=ca_bundle,
        )



    @classmethod
    def from_target(cls, fields: dict) -> PmgConfig:
        """Build a PMG config from a named registry remote (see proximo.targets)."""
        try:
            base_url = fields["base_url"]
            password_path = fields["password_path"]
        except KeyError as e:
            raise RuntimeError(f"target missing required field: {e.args[0]}") from e
        username = fields.get("username", "root@pam")
        node = fields.get("node", "pmg")
        verify_tls = parse_verify_tls(fields.get("verify_tls", "true"))
        ca_bundle = fields.get("ca_bundle") or None
        if not verify_tls and not ca_bundle:
            warnings.warn(
                "PMG target verify_tls=false with no CA bundle — "
                "talking to the PMG API without cert validation.",
                stacklevel=2,
            )
        return cls(
            base_url=base_url.rstrip("/"),
            password_path=password_path,
            username=username,
            node=node,
            verify_tls=verify_tls,
            ca_bundle=ca_bundle,
        )


# ---------------------------------------------------------------------------
# PmgBackend
# ---------------------------------------------------------------------------

class PmgBackend:
    """Management via the Proxmox Mail Gateway REST API using ticket-based auth.

    Auth flow CONFIRMED against PMG 9.1:
    - Login: POST /access/ticket with form params {username, password}
      → {ticket, CSRFPreventionToken}
    - Reads (GET): Cookie: PMGAuthCookie=<ticket>
    - Mutations (POST/PUT/DELETE): Cookie: PMGAuthCookie=<ticket>
                                   CSRFPreventionToken: <token>
    - On HTTP 401 from any call: clear the cached ticket, re-login ONCE, retry.
      If the retry also returns 401, raise_for_status raises.
    - Tickets expire (~2 h); login is lazy — first authenticated call triggers it.

    No API tokens — PMG has none of its own (the only APIToken code in PMG is its
    client for talking to a PBS backup server, not PMG's own auth).

    Self-contained: does NOT depend on ProximoConfig. Use PmgConfig.from_env()
    or construct PmgConfig directly for tests.
    """

    def __init__(self, config: PmgConfig):
        self.config = config
        verify: bool | str = config.ca_bundle if config.ca_bundle else config.verify_tls
        # FAIL-CLOSED: this backend sends credentials on login. Refuse to construct
        # over a completely unverified channel (verify_tls=False AND no ca_bundle).
        # A ca_bundle (or system CA trust) is required.
        if verify is False:
            raise ProximoError(
                "refusing to send PMG credentials over unverified TLS: set PROXIMO_PMG_CA_BUNDLE "
                "to the PMG CA cert (preferred) or PROXIMO_PMG_VERIFY_TLS=true."
            )
        self._client = httpx.Client(base_url=config.base_url, verify=httpx_verify(verify), timeout=60)
        self._ticket: str | None = None
        self._csrf: str | None = None
        self._lock = threading.Lock()

    def _login(self) -> None:
        """POST /access/ticket to obtain a session ticket and CSRF token.

        Password is read from config.password_path at call time — NEVER logged,
        never stored beyond the local scope of this method.
        """
        with open(self.config.password_path, encoding="utf-8") as f:
            password = f.read().strip()
        r = self._client.post(
            "/access/ticket",
            data={"username": self.config.username, "password": password},
        )
        r.raise_for_status()
        data = r.json()["data"]
        self._ticket = data["ticket"]
        self._csrf = data["CSRFPreventionToken"]

    def _ensure_ticket(self) -> None:
        """Lazy login — only calls _login() if no cached ticket exists.

        Uses double-checked locking so concurrent threads that both see
        ``_ticket is None`` don't each trigger a separate login: the second
        thread to acquire the lock re-checks and skips the call.
        """
        if self._ticket is None:
            with self._lock:
                if self._ticket is None:
                    self._login()

    def _cookie_headers(self) -> dict[str, str]:
        """Headers for read (GET) requests — cookie only, no CSRF."""
        return {"Cookie": f"PMGAuthCookie={self._ticket}"}

    def _mutation_headers(self) -> dict[str, str]:
        """Headers for mutation (POST/PUT/DELETE) requests — cookie + CSRF."""
        return {
            "Cookie": f"PMGAuthCookie={self._ticket}",
            "CSRFPreventionToken": self._csrf or "",
        }

    def _get(self, path: str, params: dict | None = None):
        self._ensure_ticket()
        r = self._client.get(path, headers=self._cookie_headers(), params=params or {})
        if r.status_code == 401:
            with self._lock:
                self._ticket = None
                self._csrf = None
                self._login()
            r = self._client.get(path, headers=self._cookie_headers(), params=params or {})
        r.raise_for_status()
        return r.json().get("data")

    @staticmethod
    def _form(d: dict | None) -> dict:
        # PMG (like PVE/PBS) wants booleans as 1/0; a raw Python bool serializes to 'true'/'false'
        # and may be rejected. Coerce so any tool may pass a native bool.
        return {k: (1 if v is True else 0 if v is False else v) for k, v in (d or {}).items()}

    def _post(self, path: str, data: dict | None = None):
        self._ensure_ticket()
        r = self._client.post(path, headers=self._mutation_headers(), data=self._form(data))
        if r.status_code == 401:
            with self._lock:
                self._ticket = None
                self._csrf = None
                self._login()
            r = self._client.post(path, headers=self._mutation_headers(), data=self._form(data))
        r.raise_for_status()
        return r.json().get("data")

    def _put(self, path: str, data: dict | None = None):
        self._ensure_ticket()
        r = self._client.put(path, headers=self._mutation_headers(), data=self._form(data))
        if r.status_code == 401:
            with self._lock:
                self._ticket = None
                self._csrf = None
                self._login()
            r = self._client.put(path, headers=self._mutation_headers(), data=self._form(data))
        r.raise_for_status()
        return r.json().get("data")

    def _delete(self, path: str, params: dict | None = None):
        self._ensure_ticket()
        r = self._client.delete(path, headers=self._mutation_headers(), params=params or {})
        if r.status_code == 401:
            with self._lock:
                self._ticket = None
                self._csrf = None
                self._login()
            r = self._client.delete(path, headers=self._mutation_headers(), params=params or {})
        r.raise_for_status()
        return r.json().get("data")


# ---------------------------------------------------------------------------
# READ operations — no plan needed; audited by the server layer
# ---------------------------------------------------------------------------

def node_version(api: PmgBackend, node: str) -> dict:
    """Get PMG version.

    GET /version

    PMG 9.1 live-verified: version is global (not per-node); /nodes/{node}/version
    returns 501. The ``node`` parameter is accepted for API compatibility but unused.
    """
    _check_node(node)  # validate node param even though it is not used in the path
    return api._get("/version") or {}


def access_permissions(api: PmgBackend) -> list:
    """Get users and their roles from the authenticated PMG instance.

    GET /access/users

    PMG 9.1 live-verified: PMG has no /access/permissions endpoint (that is PVE-only).
    The closest equivalent is /access/users, which returns each user's assigned role
    (e.g. 'root', 'admin', 'audit'). Used by pmg_doctor to show the credential context.
    """
    return api._get("/access/users") or []


def node_status(api: PmgBackend, node: str) -> dict:
    """Get node cpu/mem/disk/uptime status.

    GET /nodes/{node}/status

    PMG 9.1 live-verified path via pmg-smoke.py W1 (node_status round-trip PASS).
    """
    node = _check_node(node)
    return api._get(f"/nodes/{node}/status") or {}


def relay_config(api: PmgBackend) -> dict:
    """Get SMTP relay/smarthost configuration.

    GET /config/mail

    PMG 9.1 live-verified: relay/smarthost settings live in /config/mail (not a
    separate /config/relay path that does not exist). Returns the full mail section
    which includes relay host, relay port, and other SMTP delivery settings.
    """
    return api._get("/config/mail") or {}


def domains_list(api: PmgBackend) -> list[dict]:
    """List managed mail domains.

    GET /config/domains

    PMG 9.1 live-verified path via pmg-smoke.py W1 (domains_list PASS) and W3
    (domain_create → domains_list → domain_delete full cycle).
    """
    return api._get("/config/domains") or []


def statistics_mail(
    api: PmgBackend,
) -> dict:
    """Get mail delivery statistics for today (totals since midnight).

    GET /statistics/mail

    PMG 9.1 live-verified: /statistics/mail returns today's aggregate counters
    (count_in, count_out, spam, virus, bytes, …). It does NOT accept start/end
    query parameters — passing them causes HTTP 400. For time-ranged data use
    /statistics/mailcount instead.
    """
    return api._get("/statistics/mail") or {}


def quarantine_spam(
    api: PmgBackend,
) -> list[dict]:
    """List quarantined spam messages.

    GET /quarantine/spam

    PMG 9.1 live-verified: the spam quarantine list is at /quarantine/spam (not the
    non-existent /quarantine/mails). The endpoint does not accept limit/start query
    parameters — passing them causes HTTP 400.

    For virus quarantine use /quarantine/virus. For attachment quarantine use
    /quarantine/attachment.
    """
    return api._get("/quarantine/spam") or []


# ---------------------------------------------------------------------------
# MUTATION operations — confirm-gated at the server layer
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# PLAN functions — pure factories; no mutation; the PLAN pillar
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# W2 READ operations
# ---------------------------------------------------------------------------

def statistics_domains(
    api: PmgBackend,
    start: int | None = None,
    end: int | None = None,
) -> list[dict]:
    """Get per-domain mail statistics.

    GET /statistics/domains

    PMG 9.1 live-verified path via pmgsh ls.
    Maps tool start/end epoch params → starttime/endtime query params.
    """
    if start is not None:
        try:
            int(start)
        except (ValueError, TypeError) as exc:
            raise ProximoError(
                f"invalid start: {start!r} (must be an integer Unix epoch)"
            ) from exc
    if end is not None:
        try:
            int(end)
        except (ValueError, TypeError) as exc:
            raise ProximoError(
                f"invalid end: {end!r} (must be an integer Unix epoch)"
            ) from exc
    params: dict = {}
    if start is not None:
        params["starttime"] = int(start)
    if end is not None:
        params["endtime"] = int(end)
    return api._get("/statistics/domains", params=params if params else None) or []


def statistics_virus(
    api: PmgBackend,
    start: int | None = None,
    end: int | None = None,
) -> list[dict]:
    """Get virus statistics.

    GET /statistics/virus

    PMG 9.1 live-verified path via pmgsh ls.
    Maps tool start/end epoch params → starttime/endtime query params.
    """
    if start is not None:
        try:
            int(start)
        except (ValueError, TypeError) as exc:
            raise ProximoError(
                f"invalid start: {start!r} (must be an integer Unix epoch)"
            ) from exc
    if end is not None:
        try:
            int(end)
        except (ValueError, TypeError) as exc:
            raise ProximoError(
                f"invalid end: {end!r} (must be an integer Unix epoch)"
            ) from exc
    params: dict = {}
    if start is not None:
        params["starttime"] = int(start)
    if end is not None:
        params["endtime"] = int(end)
    return api._get("/statistics/virus", params=params if params else None) or []


def statistics_spamscores(
    api: PmgBackend,
    start: int | None = None,
    end: int | None = None,
) -> list[dict]:
    """Get spam score distribution statistics.

    GET /statistics/spamscores

    PMG 9.1 live-verified path via pmgsh ls.
    Maps tool start/end epoch params → starttime/endtime query params.
    """
    if start is not None:
        try:
            int(start)
        except (ValueError, TypeError) as exc:
            raise ProximoError(
                f"invalid start: {start!r} (must be an integer Unix epoch)"
            ) from exc
    if end is not None:
        try:
            int(end)
        except (ValueError, TypeError) as exc:
            raise ProximoError(
                f"invalid end: {end!r} (must be an integer Unix epoch)"
            ) from exc
    params: dict = {}
    if start is not None:
        params["starttime"] = int(start)
    if end is not None:
        params["endtime"] = int(end)
    return api._get("/statistics/spamscores", params=params if params else None) or []


def statistics_recent(api: PmgBackend, hours: int = 1) -> list[dict]:
    """Get recent mail statistics.

    GET /statistics/recent

    PMG 9.1 live-verified path via pmgsh ls.
    hours: 1-24 (window of recent mail activity to retrieve).
    """
    try:
        h = int(hours)
    except (ValueError, TypeError) as exc:
        raise ProximoError(f"invalid hours: {hours!r} — must be an integer") from exc
    return api._get("/statistics/recent", params={"hours": h}) or []


def quarantine_blocklist_list(
    api: PmgBackend,
    pmail: str | None = None,
) -> list[dict]:
    """List blocklist entries.

    GET /quarantine/blocklist

    PMG 9.1 live-verified: the API requires pmail for root@pam (and scopes
    the result to that user's blocklist for non-root users). When pmail is
    not provided it defaults to api.config.username (the authenticated user).
    pmail: optional per-user mail address — overrides the default username scope.
    """
    effective_pmail = pmail if pmail is not None else api.config.username
    return api._get("/quarantine/blocklist", params={"pmail": effective_pmail}) or []


def postfix_qshape(api: PmgBackend, node: str) -> list[dict]:
    """Get Postfix queue shape (queue sizes and message-age distribution).

    GET /nodes/{node}/postfix/qshape

    PMG 9.1 live-verified: returns a list of dicts, one row per domain
    (plus a TOTAL row), each with queue-age bucket counts.
    """
    node = _check_node(node)
    return api._get(f"/nodes/{node}/postfix/qshape") or []


def spam_config(api: PmgBackend) -> dict:
    """Get PMG spam filter configuration.

    GET /config/spam

    PMG 9.1 live-verified path via pmgsh ls.
    """
    return api._get("/config/spam") or {}


def service_status(api: PmgBackend, service: str, node: str | None = None) -> dict:
    """Get the status of a PMG system service.

    GET /nodes/{node}/services/{service}/state

    PMG 9.1 live-verified path via pmgsh ls.
    service: service name (e.g. 'postfix', 'pmgproxy', 'pmgdaemon', 'pmgmirror',
             'pmgtunnel', 'pmg-smtp-filter', 'clamav', 'spamassassin').
             No hardcoded enum — any valid name is accepted; unknown names return
             a PMG 404. Must be alphanumeric + hyphen (no path traversal).
    """
    service = _check_service(service)
    node = _check_node(node or "pmg")
    return api._get(f"/nodes/{node}/services/{service}/state") or {}


# ---------------------------------------------------------------------------
# W2 MUTATION operations — confirm-gated at the server layer
# ---------------------------------------------------------------------------

def quarantine_blocklist_add(
    api: PmgBackend,
    address: str,
    pmail: str | None = None,
) -> object:
    """Add an address to the quarantine blocklist.

    POST /quarantine/blocklist

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 live-verified: pmail is required by PMG for root@pam (and scopes
    the entry to that user's blocklist for non-root users). When pmail is not
    provided it defaults to api.config.username.
    address: the email address or domain to blocklist.
    pmail: optional per-user mail address — overrides the default username scope.
    """
    effective_pmail = pmail if pmail is not None else api.config.username
    body: dict = {"address": address, "pmail": effective_pmail}
    return api._post("/quarantine/blocklist", data=body)


def quarantine_blocklist_remove(
    api: PmgBackend,
    address: str,
    pmail: str | None = None,
) -> object:
    """Remove an address from the quarantine blocklist.

    DELETE /quarantine/blocklist?address=<address>&pmail=<pmail>

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 live-verified: the delete is issued via DELETE /quarantine/blocklist
    with address and pmail as query parameters (not a path segment — PMG 9.1
    returns 501 for DELETE /quarantine/blocklist/{address}).
    When pmail is not provided it defaults to api.config.username.
    """
    effective_pmail = pmail if pmail is not None else api.config.username
    return api._delete("/quarantine/blocklist",
                       params={"address": address, "pmail": effective_pmail})


def quarantine_action(
    api: PmgBackend,
    action: str,
    mail_ids: str,
) -> object:
    """Apply an action to one or more quarantined messages.

    POST /quarantine/content

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 live-proven 2026-06-26: path via pmgsh ls + delete/deliver executed
    against real quarantined GTUBE messages.
    action: one of deliver|delete|mark-seen|mark-unseen|blocklist|welcomelist.
    mail_ids: mail ID or comma-separated list of mail IDs to act on.
    """
    if action not in _QUARANTINE_ACTIONS:
        raise ProximoError(
            f"invalid quarantine action: {action!r}. "
            f"Must be one of: {', '.join(sorted(_QUARANTINE_ACTIONS))}"
        )
    return api._post("/quarantine/content", data={"action": action, "id": mail_ids})


def postfix_flush(api: PmgBackend, node: str) -> object:
    """Flush all Postfix queues (attempt immediate re-delivery of deferred mail).

    POST /nodes/{node}/postfix/flush_queues

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 live-verified path via pmgsh ls.
    """
    node = _check_node(node)
    return api._post(f"/nodes/{node}/postfix/flush_queues")


# ---------------------------------------------------------------------------
# W2 PLAN functions — pure factories; no mutation; the PLAN pillar
# ---------------------------------------------------------------------------

def plan_quarantine_blocklist_add(address: str, pmail: str | None = None) -> Plan:
    """Preview adding an address to the quarantine blocklist.  PURE — no API call.

    RISK_LOW: adds an entry to the blocklist; does not delete any existing messages.
    Only future mail from the address is affected.
    """
    scope = f" for {pmail}" if pmail else " (global)"
    return Plan(
        action="pmg_quarantine_blocklist_add",
        target="quarantine/blocklist",
        change=f"add '{address}' to the quarantine blocklist{scope}",
        current={},
        blast_radius=[
            f"future messages from '{address}' will be blocked and quarantined",
            f"scope: {'per-user (' + pmail + ')' if pmail else 'global blocklist (all users)'}",
            "additive: does not delete any existing quarantine entries or messages",
            "only future inbound mail matching this address/domain is affected",
        ],
        risk=RISK_LOW,
        risk_reasons=[
            "additive: adds one blocklist entry; no messages or data deleted",
            "LOW: only future mail is affected, not existing quarantine or mailbox contents",
        ],
        note="PMG 9.1 live-verified path via pmgsh ls: POST /quarantine/blocklist.",
    )


def plan_quarantine_action(action: str, mail_ids: str) -> Plan:
    """Preview applying an action to quarantined messages.  PURE — no API call.

    RISK_MEDIUM: action may be destructive (e.g. delete permanently removes messages).
    Validates the action enum before building the plan.
    """
    if action not in _QUARANTINE_ACTIONS:
        raise ProximoError(
            f"invalid quarantine action: {action!r}. "
            f"Must be one of: {', '.join(sorted(_QUARANTINE_ACTIONS))}"
        )
    return Plan(
        action="pmg_quarantine_action",
        target="quarantine/content",
        change=f"apply action '{action}' to quarantined message(s): {mail_ids}",
        current={},
        blast_radius=[
            f"action '{action}' applied to: {mail_ids}",
            "deliver: releases message(s) to recipient(s) — additive, no quarantine data deleted",
            "delete: permanently removes message(s) from quarantine — IRREVERSIBLE",
            "mark-seen/mark-unseen: metadata change only — no messages delivered or deleted",
            "blocklist/welcomelist: adds sender to the respective list — additive",
            "live-proven 2026-06-26: delete and deliver both confirmed on real GTUBE messages",
        ],
        risk=RISK_HIGH if action == "delete" else RISK_MEDIUM,
        risk_reasons=[
            "HIGH for action='delete': permanently and irreversibly removes quarantined messages",
            "other actions (deliver, mark-*, blocklist, welcomelist) are MEDIUM — reversible or additive",
        ],
        note=(
            "PMG 9.1 live-proven 2026-06-26: POST /quarantine/content with action=delete "
            "and action=deliver both execute correctly against real quarantined messages. "
            "delete: entry permanently removed. deliver: entry removed, message released."
        ),
    )


def plan_postfix_flush(node: str) -> Plan:
    """Preview flushing all Postfix queues.  PURE — no API call.

    RISK_LOW: attempts immediate re-delivery of deferred mail; no data is deleted.
    """
    node = _check_node(node)
    return Plan(
        action="pmg_postfix_flush",
        target=f"pmg/{node}/postfix/flush_queues",
        change=f"flush all Postfix mail queues on node '{node}'",
        current={},
        blast_radius=[
            f"triggers immediate re-delivery attempt for all deferred mail on '{node}'",
            "may cause a burst of outbound SMTP connections during the flush",
            "no messages are deleted — deferred mail that cannot be delivered stays deferred",
            "additive: queue flush is a standard mail server operation",
        ],
        risk=RISK_LOW,
        risk_reasons=[
            "additive: no mail is deleted; flush only attempts re-delivery of deferred messages",
            "LOW: standard Postfix operation; temporary connection burst is expected behavior",
        ],
        note="PMG 9.1 live-verified path via pmgsh ls: POST /nodes/{node}/postfix/flush_queues.",
    )


# ---------------------------------------------------------------------------
# W3 READ operations
# ---------------------------------------------------------------------------

def quarantine_welcomelist_list(
    api: PmgBackend,
    pmail: str | None = None,
) -> list[dict]:
    """List quarantine welcomelist entries.

    GET /quarantine/welcomelist

    PMG 9.1 live-verified path via pmgsh ls.
    pmail: optional per-user mail address — scopes the list to that user.
    When pmail is not provided it defaults to api.config.username (PMG requires it for root@pam).
    """
    effective_pmail = pmail if pmail is not None else api.config.username
    return api._get("/quarantine/welcomelist", params={"pmail": effective_pmail}) or []


# ---------------------------------------------------------------------------
# W3 MUTATION operations — confirm-gated at the server layer
# ---------------------------------------------------------------------------

def domain_create(api: PmgBackend, domain: str, comment: str | None = None) -> object:
    """Create a managed mail domain.

    POST /config/domains

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 live-verified path via pmgsh ls.
    domain: domain name to manage (e.g. 'example.com').
    """
    domain = _check_domain(domain)
    body: dict = {"domain": domain}
    if comment is not None:
        body["comment"] = comment
    return api._post("/config/domains", data=body)


def domain_delete(api: PmgBackend, domain: str) -> object:
    """Delete a managed mail domain.

    DELETE /config/domains/{domain}

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 live-verified path via pmgsh ls.
    """
    domain = _check_domain(domain)
    return api._delete(f"/config/domains/{domain}")


def transport_create(
    api: PmgBackend,
    domain: str,
    host: str,
    comment: str | None = None,
    port: int = 25,
    protocol: str = "smtp",
    use_mx: bool = True,
) -> object:
    """Create a mail transport rule.

    POST /config/transport

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 live-verified path via pmgsh ls.
    domain: destination domain for this transport rule.
    host: next-hop relay host.
    port: TCP port (1-65535, default 25).
    protocol: smtp or lmtp (default smtp).
    use_mx: use MX lookup for the host (default True).
    """
    domain = _check_domain(domain)
    protocol = _check_transport_protocol(protocol)
    try:
        port_int = int(port)
    except (ValueError, TypeError) as exc:
        raise ProximoError(f"invalid port: {port!r} — must be an integer") from exc
    if not (1 <= port_int <= 65535):
        raise ProximoError(
            f"invalid port: {port!r} — must be an integer in 1-65535"
        )
    body: dict = {
        "domain": domain, "host": host, "port": port_int,
        "protocol": protocol, "use_mx": use_mx,
    }
    if comment is not None:
        body["comment"] = comment
    return api._post("/config/transport", data=body)


def transport_delete(api: PmgBackend, domain: str) -> object:
    """Delete a mail transport rule.

    DELETE /config/transport/{domain}

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 live-verified path via pmgsh ls.
    """
    domain = _check_domain(domain)
    return api._delete(f"/config/transport/{domain}")


def mynetworks_add(api: PmgBackend, cidr: str, comment: str | None = None) -> object:
    """Add a network to the PMG mynetworks (trusted relay) list.

    POST /config/mynetworks

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 live-verified path via pmgsh ls.
    cidr: network in CIDR notation (e.g. '10.0.0.0/8').
    """
    cidr = _check_cidr(cidr)
    body: dict = {"cidr": cidr}
    if comment is not None:
        body["comment"] = comment
    return api._post("/config/mynetworks", data=body)


def mynetworks_remove(api: PmgBackend, cidr: str) -> object:
    """Remove a network from the PMG mynetworks (trusted relay) list.

    DELETE /config/mynetworks/{cidr}  (cidr is URL-encoded: / → %2F)

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 live-verified path via pmgsh ls.
    The slash in the CIDR is percent-encoded so PMG does not treat it as a path separator.
    """
    cidr = _check_cidr(cidr)
    encoded = quote(cidr, safe="")
    return api._delete(f"/config/mynetworks/{encoded}")


def spam_config_update(
    api: PmgBackend,
    bounce_score: int | None = None,
    clamav_heuristic_score: int | None = None,
    extract_text: bool | None = None,
    languages: str | None = None,
    maxspamsize: int | None = None,
    rbl_checks: bool | None = None,
    use_awl: bool | None = None,
    use_bayes: bool | None = None,
    use_razor: bool | None = None,
    wl_bounce_relays: str | None = None,
    delete: str | None = None,
) -> object:
    """Update PMG spam filter configuration.

    PUT /config/spam

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 live-verified path via pmgsh ls.
    Only fields that are not None are sent — PMG keeps omitted fields at their current values.
    Bool fields are coerced to 1/0 by PmgBackend._put → _form (PMG API expects integers).
    delete: comma-separated list of field names to reset to their defaults.
    """
    # Filter None values before building the body — sending null would override PMG defaults.
    body = {k: v for k, v in {
        "bounce_score": bounce_score,
        "clamav_heuristic_score": clamav_heuristic_score,
        "extract_text": extract_text,
        "languages": languages,
        "maxspamsize": maxspamsize,
        "rbl_checks": rbl_checks,
        "use_awl": use_awl,
        "use_bayes": use_bayes,
        "use_razor": use_razor,
        "wl_bounce_relays": wl_bounce_relays,
        "delete": delete,
    }.items() if v is not None}
    return api._put("/config/spam", data=body)


def quarantine_welcomelist_add(
    api: PmgBackend,
    address: str,
    pmail: str | None = None,
) -> object:
    """Add an address to the quarantine welcomelist.

    POST /quarantine/welcomelist

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 live-verified path via pmgsh ls.
    address: email address or domain to add.
    pmail: optional per-user mail address — defaults to api.config.username.
    """
    effective_pmail = pmail if pmail is not None else api.config.username
    body: dict = {"address": address, "pmail": effective_pmail}
    return api._post("/quarantine/welcomelist", data=body)


def quarantine_welcomelist_remove(
    api: PmgBackend,
    address: str,
    pmail: str | None = None,
) -> object:
    """Remove an address from the quarantine welcomelist.

    DELETE /quarantine/welcomelist  (address + pmail as query params, not a path segment)

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 live-verified path via pmgsh ls.
    When pmail is not provided it defaults to api.config.username.
    """
    effective_pmail = pmail if pmail is not None else api.config.username
    return api._delete("/quarantine/welcomelist",
                       params={"address": address, "pmail": effective_pmail})


def service_control(
    api: PmgBackend,
    service: str,
    action: str,
    node: str | None = None,
) -> object:
    """Start, stop, restart, or reload a PMG system service.

    POST /nodes/{node}/services/{service}/{action}

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 live-verified path via pmgsh ls.
    service: service name (e.g. 'postfix', 'pmgproxy', 'pmgdaemon').
             Validated against the service-name charset (no path traversal).
    action: start|stop|restart|reload.
    WARNING: stop on postfix/pmgproxy/pmgdaemon interrupts mail delivery until manually restarted.
    """
    service = _check_service(service)
    action = _check_service_action(action)
    effective_node = _check_node(node or "pmg")
    return api._post(f"/nodes/{effective_node}/services/{service}/{action}")


# ---------------------------------------------------------------------------
# W3 PLAN functions — pure factories; no mutation; the PLAN pillar
# ---------------------------------------------------------------------------

def plan_domain_create(domain: str, comment: str | None = None) -> Plan:
    """Preview creating a managed mail domain.  PURE — no API call.

    RISK_LOW: additive — adds a domain entry; does not affect existing mail flow.
    """
    domain = _check_domain(domain)
    return Plan(
        action="pmg_domain_create",
        target="config/domains",
        change=f"create managed mail domain '{domain}'",
        current={},
        blast_radius=[
            f"adds '{domain}' to PMG's managed mail domain list",
            "additive: does not affect existing domains or current mail flow",
            "the domain becomes available for routing and filter rules",
        ],
        risk=RISK_LOW,
        risk_reasons=[
            "additive: creates one domain entry; no existing config or mail deleted",
            "LOW: new domain is inactive until routing rules reference it",
        ],
        note="PMG 9.1 live-verified path via pmgsh ls: POST /config/domains.",
    )


def plan_domain_delete(domain: str) -> Plan:
    """Preview deleting a managed mail domain.  PURE — no API call.

    RISK_MEDIUM: removes a domain configuration; mail routing may be affected.
    """
    domain = _check_domain(domain)
    return Plan(
        action="pmg_domain_delete",
        target=f"config/domains/{domain}",
        change=f"delete managed mail domain '{domain}'",
        current={},
        blast_radius=[
            f"removes '{domain}' from PMG's managed mail domain list",
            "mail routing rules referencing this domain may break after deletion",
            "review dependent transport and filter rules before removing a domain",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=[
            "MEDIUM: removes a domain; routing rules referencing it may stop working",
            "review dependent transport and filter rules before confirming",
        ],
        note="PMG 9.1 live-verified path via pmgsh ls: DELETE /config/domains/{domain}.",
    )


def plan_transport_create(
    domain: str,
    host: str,
    comment: str | None = None,
    port: int = 25,
    protocol: str = "smtp",
    use_mx: bool = True,
) -> Plan:
    """Preview creating a mail transport rule.  PURE — no API call.

    RISK_LOW: additive — adds a transport rule; does not affect existing rules.
    """
    domain = _check_domain(domain)
    protocol = _check_transport_protocol(protocol)
    return Plan(
        action="pmg_transport_create",
        target="config/transport",
        change=f"create transport rule: '{domain}' → '{host}:{port}' via {protocol}",
        current={},
        blast_radius=[
            f"mail for '{domain}' will be routed to '{host}' on port {port} via {protocol}",
            f"MX lookup: {'enabled' if use_mx else 'disabled'}",
            "additive: does not change routing for other domains",
        ],
        risk=RISK_LOW,
        risk_reasons=[
            "additive: creates one transport rule; no existing rules or mail deleted",
            "LOW: affects only new mail routing for the specified domain",
        ],
        note="PMG 9.1 live-verified path via pmgsh ls: POST /config/transport.",
    )


def plan_transport_delete(domain: str) -> Plan:
    """Preview deleting a mail transport rule.  PURE — no API call.

    RISK_MEDIUM: removes an explicit routing rule; mail may fall back to default routing.
    """
    domain = _check_domain(domain)
    return Plan(
        action="pmg_transport_delete",
        target=f"config/transport/{domain}",
        change=f"delete transport rule for domain '{domain}'",
        current={},
        blast_radius=[
            f"removes the explicit transport rule for '{domain}'",
            f"mail for '{domain}' will fall back to PMG's default routing (MX lookup)",
            "verify fallback routing is intentional before confirming",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=[
            "MEDIUM: removes an explicit routing rule; fallback routing takes over",
            "if the domain requires special routing, removal may cause misdelivery",
        ],
        note="PMG 9.1 live-verified path via pmgsh ls: DELETE /config/transport/{domain}.",
    )


def plan_mynetworks_add(cidr: str, comment: str | None = None) -> Plan:
    """Preview adding a network to the PMG mynetworks trusted relay list.  PURE — no API call.

    RISK_LOW: additive — grants trusted relay status to a CIDR range.
    """
    cidr = _check_cidr(cidr)
    return Plan(
        action="pmg_mynetworks_add",
        target="config/mynetworks",
        change=f"add '{cidr}' to PMG trusted relay (mynetworks) list",
        current={},
        blast_radius=[
            f"hosts in '{cidr}' will be trusted as relay senders (may bypass spam checks)",
            "only add CIDRs you control — trusted relays can reduce filtering effectiveness",
            "additive: does not affect existing mynetworks entries",
        ],
        risk=RISK_LOW,
        risk_reasons=[
            "additive: adds one network entry; no existing config or mail deleted",
            "LOW: effect is to trust a new IP range as a relay — review the CIDR carefully",
        ],
        note="PMG 9.1 live-verified path via pmgsh ls: POST /config/mynetworks.",
    )


def plan_mynetworks_remove(cidr: str) -> Plan:
    """Preview removing a network from the PMG mynetworks trusted relay list.  PURE — no API call.

    RISK_MEDIUM: removes trusted relay status; hosts in the CIDR become subject to filtering.
    """
    cidr = _check_cidr(cidr)
    return Plan(
        action="pmg_mynetworks_remove",
        target="config/mynetworks",
        change=f"remove '{cidr}' from PMG trusted relay (mynetworks) list",
        current={},
        blast_radius=[
            f"hosts in '{cidr}' will no longer be trusted as relay senders",
            "mail from those hosts will be subject to spam/RBL filtering",
            "internal mail servers in this range will need an alternative relay path",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=[
            "MEDIUM: removes relay trust; internal senders in the range may be rejected",
            "verify no production mail servers are in this range before confirming",
        ],
        note="PMG 9.1 live-verified path via pmgsh ls: DELETE /config/mynetworks/{cidr}.",
    )


def plan_spam_config_update(**kwargs: object) -> Plan:
    """Preview updating PMG spam filter configuration.  PURE — no API call.

    RISK_MEDIUM: changes spam filtering behavior; affects all inbound mail immediately.
    Raises ProximoError if no fields are provided (all-None update is a no-op).
    """
    # Filter Nones — the same logic the op uses before building the PUT body.
    changes = {k: v for k, v in kwargs.items() if v is not None}
    if not changes:
        raise ProximoError(
            "pmg_spam_config_update: at least one field must be provided "
            "(all values are None — nothing to update)"
        )
    change_summary = "; ".join(f"{k}={v!r}" for k, v in sorted(changes.items()))
    return Plan(
        action="pmg_spam_config_update",
        target="config/spam",
        change=f"update spam filter configuration: {change_summary}",
        current={},
        blast_radius=[
            "spam scoring/filtering changes take effect immediately on new inbound mail",
            "lowering thresholds may cause legitimate mail to be quarantined (false positives)",
            "raising thresholds may allow more spam through (false negatives)",
            f"fields being changed: {', '.join(sorted(changes.keys()))}",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=[
            "MEDIUM: spam filter changes affect all inbound mail immediately",
            "incorrect thresholds can cause false positives or false negatives at scale",
        ],
        note="PMG 9.1 live-verified path via pmgsh ls: PUT /config/spam.",
    )


def plan_quarantine_welcomelist_add(address: str, pmail: str | None = None) -> Plan:
    """Preview adding an address to the quarantine welcomelist.  PURE — no API call.

    RISK_LOW: additive — adds a welcomelist entry; future mail from the address bypasses quarantine.
    """
    scope = f" for {pmail}" if pmail else " (global)"
    return Plan(
        action="pmg_quarantine_welcomelist_add",
        target="quarantine/welcomelist",
        change=f"add '{address}' to the quarantine welcomelist{scope}",
        current={},
        blast_radius=[
            f"future messages from '{address}' will bypass quarantine checks",
            f"scope: {'per-user (' + pmail + ')' if pmail else 'global (all users)'}",
            "additive: does not delete any existing quarantine entries or messages",
            "only future inbound mail matching this address/domain is affected",
        ],
        risk=RISK_LOW,
        risk_reasons=[
            "additive: adds one welcomelist entry; no messages or data deleted",
            "LOW: only future mail is affected, not existing quarantine or mailbox contents",
        ],
        note="PMG 9.1 live-verified path via pmgsh ls: POST /quarantine/welcomelist.",
    )


def plan_quarantine_welcomelist_remove(address: str, pmail: str | None = None) -> Plan:
    """Preview removing an address from the quarantine welcomelist.  PURE — no API call.

    RISK_LOW: removes a welcomelist entry; mail from the address is re-evaluated normally.
    """
    scope = f" for {pmail}" if pmail else " (global)"
    return Plan(
        action="pmg_quarantine_welcomelist_remove",
        target="quarantine/welcomelist",
        change=f"remove '{address}' from the quarantine welcomelist{scope}",
        current={},
        blast_radius=[
            f"future messages from '{address}' will again be subject to spam/quarantine checks",
            f"scope: {'per-user (' + pmail + ')' if pmail else 'global (all users)'}",
            "existing quarantine state is unaffected — only future mail is re-evaluated",
        ],
        risk=RISK_LOW,
        risk_reasons=[
            "LOW: removes one welcomelist entry; no messages deleted",
            "mail from the address will be spam-filtered again going forward",
        ],
        note="PMG 9.1 live-verified path via pmgsh ls: DELETE /quarantine/welcomelist.",
    )


def plan_quarantine_blocklist_remove(address: str, pmail: str | None = None) -> Plan:
    """Preview removing an address from the quarantine blocklist.  PURE — no API call.

    RISK_LOW: removes a blocklist entry; mail from the address will be re-evaluated normally.

    The executor (quarantine_blocklist_remove) was added in W2; this plan function
    completes the PLAN pillar so the server tool can gate with dry-run.
    """
    scope = f" for {pmail}" if pmail else " (global)"
    return Plan(
        action="pmg_quarantine_blocklist_remove",
        target="quarantine/blocklist",
        change=f"remove '{address}' from the quarantine blocklist{scope}",
        current={},
        blast_radius=[
            f"future messages from '{address}' will no longer be automatically blocked",
            f"scope: {'per-user (' + pmail + ')' if pmail else 'global (all users)'}",
            "existing quarantine entries are unaffected — only future mail is re-evaluated",
        ],
        risk=RISK_LOW,
        risk_reasons=[
            "LOW: removes one blocklist entry; no messages deleted",
            "mail from the address will be spam-filtered normally going forward",
        ],
        note="PMG 9.1 live-verified path via pmgsh ls: DELETE /quarantine/blocklist.",
    )


def plan_service_control(service: str, action: str, node: str | None = None) -> Plan:
    """Preview starting, stopping, restarting, or reloading a PMG service.  PURE — no API call.

    RISK_MEDIUM: stop/restart of core services interrupts mail delivery.
    Validates the action enum before building the plan.
    """
    service = _check_service(service)
    action = _check_service_action(action)
    effective_node = node or "pmg"
    return Plan(
        action="pmg_service_control",
        target=f"pmg/{effective_node}/services/{service}/{action}",
        change=f"{action} service '{service}' on PMG node '{effective_node}'",
        current={},
        blast_radius=[
            f"service '{service}' will be {action}ed on node '{effective_node}'",
            "stop on postfix/pmgproxy/pmgdaemon interrupts mail delivery until manually restarted",
            "restart causes a brief service interruption; reload is typically non-disruptive",
            "start on a stopped service resumes mail processing",
            "effect is immediate on the live running service",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=[
            "MEDIUM: stop/restart of postfix or pmg core services halts mail delivery",
            "service outage may persist until the service is manually restarted if start fails",
        ],
        note="PMG 9.1 live-verified path via pmgsh ls: POST /nodes/{node}/services/{service}/{action}.",
    )


# ---------------------------------------------------------------------------
# W4 Validators
# ---------------------------------------------------------------------------

# RRD timeframe values (PMG 9.1 live-verified).
_RRDDATA_TIMEFRAMES = frozenset({"hour", "day", "week", "month", "year"})


def _check_rrddata_timeframe(timeframe: str) -> str:
    s = str(timeframe)
    if s not in _RRDDATA_TIMEFRAMES:
        raise ProximoError(
            f"invalid rrddata timeframe: {timeframe!r}. "
            f"Must be one of: {', '.join(sorted(_RRDDATA_TIMEFRAMES))}"
        )
    return s


# RRD consolidation function values (PMG 9.1 live-verified).
_RRDDATA_CF = frozenset({"AVERAGE", "MAX"})


def _check_rrddata_cf(cf: str) -> str:
    s = str(cf)
    if s not in _RRDDATA_CF:
        raise ProximoError(
            f"invalid rrddata cf: {cf!r}. "
            f"Must be one of: {', '.join(sorted(_RRDDATA_CF))}"
        )
    return s


# Backup notify values (PMG 9.1 live-verified).
_NOTIFY_VALUES = frozenset({"always", "error", "never"})


def _check_backup_notify(notify: str) -> str:
    s = str(notify)
    if s not in _NOTIFY_VALUES:
        raise ProximoError(
            f"invalid backup notify: {notify!r}. "
            f"Must be one of: {', '.join(sorted(_NOTIFY_VALUES))}"
        )
    return s


# Quarantine type values (PMG 9.1 live-verified: /quarantine/spamusers quarantine-type param).
_QUARANTINE_TYPE_VALUES = frozenset({"attachment", "spam", "virus"})


def _check_quarantine_type(quarantine_type: str) -> str:
    s = str(quarantine_type)
    if s not in _QUARANTINE_TYPE_VALUES:
        raise ProximoError(
            f"invalid quarantine_type: {quarantine_type!r}. "
            f"Must be one of: {', '.join(sorted(_QUARANTINE_TYPE_VALUES))}"
        )
    return s


# ---------------------------------------------------------------------------
# W4 READ operations
# ---------------------------------------------------------------------------


def tracker_list(
    api: PmgBackend,
    node: str,
    start: int | None = None,
    end: int | None = None,
    from_: str | None = None,
    target: str | None = None,
    xfilter: str | None = None,
    ndr: bool | None = None,
    greylist: bool | None = None,
    limit: int = 2000,
) -> list[dict]:
    """List mail tracking entries.

    GET /nodes/{node}/tracker

    PMG 9.1 live-verified path via pmgsh ls.
    Maps start/end epoch params → starttime/endtime query params.
    from_: envelope-sender filter (Python keyword-safe alias for 'from').
    limit: max results 0–100000 (default 2000).
    """
    node = _check_node(node)
    if start is not None:
        try:
            int(start)
        except (ValueError, TypeError) as exc:
            raise ProximoError(
                f"invalid start: {start!r} (must be an integer Unix epoch)"
            ) from exc
    if end is not None:
        try:
            int(end)
        except (ValueError, TypeError) as exc:
            raise ProximoError(
                f"invalid end: {end!r} (must be an integer Unix epoch)"
            ) from exc
    params: dict = {"limit": int(limit)}
    if start is not None:
        params["starttime"] = int(start)
    if end is not None:
        params["endtime"] = int(end)
    if from_ is not None:
        params["from"] = from_
    if target is not None:
        params["target"] = target
    if xfilter is not None:
        params["xfilter"] = xfilter
    if ndr is not None:
        params["ndr"] = 1 if ndr else 0
    if greylist is not None:
        params["greylist"] = 1 if greylist else 0
    return api._get(f"/nodes/{node}/tracker", params=params) or []


def tracker_detail(
    api: PmgBackend,
    node: str,
    id_: str,
    start: int | None = None,
    end: int | None = None,
) -> list[dict]:
    """Get tracking detail for a specific mail ID.

    GET /nodes/{node}/tracker/{id}

    PMG 9.1 live-verified path via pmgsh ls.
    id_: mail/queue tracker ID, validated path-segment-safe (no traversal/injection metachars).
    Maps start/end epoch params → starttime/endtime query params.
    """
    node = _check_node(node)
    id_ = _check_tracker_id(id_)
    if start is not None:
        try:
            int(start)
        except (ValueError, TypeError) as exc:
            raise ProximoError(
                f"invalid start: {start!r} (must be an integer Unix epoch)"
            ) from exc
    if end is not None:
        try:
            int(end)
        except (ValueError, TypeError) as exc:
            raise ProximoError(
                f"invalid end: {end!r} (must be an integer Unix epoch)"
            ) from exc
    params: dict = {}
    if start is not None:
        params["starttime"] = int(start)
    if end is not None:
        params["endtime"] = int(end)
    return api._get(
        f"/nodes/{node}/tracker/{id_}", params=params if params else None
    ) or []


def quarantine_virus(
    api: PmgBackend,
    pmail: str | None = None,
    start: int | None = None,
    end: int | None = None,
) -> list[dict]:
    """List virus quarantine entries.

    GET /quarantine/virus

    PMG 9.1 live-verified path via pmgsh ls.
    pmail: per-user scope — defaults to api.config.username (mirrors W2 blocklist pattern).
    Maps start/end epoch params → starttime/endtime query params.
    """
    effective_pmail = pmail if pmail is not None else api.config.username
    if start is not None:
        try:
            int(start)
        except (ValueError, TypeError) as exc:
            raise ProximoError(
                f"invalid start: {start!r} (must be an integer Unix epoch)"
            ) from exc
    if end is not None:
        try:
            int(end)
        except (ValueError, TypeError) as exc:
            raise ProximoError(
                f"invalid end: {end!r} (must be an integer Unix epoch)"
            ) from exc
    params: dict = {"pmail": effective_pmail}
    if start is not None:
        params["starttime"] = int(start)
    if end is not None:
        params["endtime"] = int(end)
    return api._get("/quarantine/virus", params=params) or []


def quarantine_attachment(
    api: PmgBackend,
    pmail: str | None = None,
    start: int | None = None,
    end: int | None = None,
) -> list[dict]:
    """List attachment quarantine entries.

    GET /quarantine/attachment

    PMG 9.1 live-verified path via pmgsh ls.
    pmail: per-user scope — defaults to api.config.username (mirrors W2 blocklist pattern).
    Maps start/end epoch params → starttime/endtime query params.
    """
    effective_pmail = pmail if pmail is not None else api.config.username
    if start is not None:
        try:
            int(start)
        except (ValueError, TypeError) as exc:
            raise ProximoError(
                f"invalid start: {start!r} (must be an integer Unix epoch)"
            ) from exc
    if end is not None:
        try:
            int(end)
        except (ValueError, TypeError) as exc:
            raise ProximoError(
                f"invalid end: {end!r} (must be an integer Unix epoch)"
            ) from exc
    params: dict = {"pmail": effective_pmail}
    if start is not None:
        params["starttime"] = int(start)
    if end is not None:
        params["endtime"] = int(end)
    return api._get("/quarantine/attachment", params=params) or []


def quarantine_virusstatus(api: PmgBackend) -> dict:
    """Get virus quarantine status summary.

    GET /quarantine/virusstatus

    PMG 9.1 live-verified path via pmgsh ls.
    """
    return api._get("/quarantine/virusstatus") or {}


def quarantine_spamstatus(api: PmgBackend) -> dict:
    """Get spam quarantine status summary.

    GET /quarantine/spamstatus

    PMG 9.1 live-verified path via pmgsh ls.
    """
    return api._get("/quarantine/spamstatus") or {}


def quarantine_spamusers(
    api: PmgBackend,
    start: int | None = None,
    end: int | None = None,
    quarantine_type: str = "spam",
) -> list[dict]:
    """List users with quarantined mail entries.

    GET /quarantine/spamusers

    PMG 9.1 live-verified path via pmgsh ls.
    quarantine_type: spam|virus|attachment (default spam).
    NOTE: Python arg 'quarantine_type' maps to API param 'quarantine-type' (hyphen).
    Maps start/end epoch params → starttime/endtime query params.
    """
    quarantine_type = _check_quarantine_type(quarantine_type)
    if start is not None:
        try:
            int(start)
        except (ValueError, TypeError) as exc:
            raise ProximoError(
                f"invalid start: {start!r} (must be an integer Unix epoch)"
            ) from exc
    if end is not None:
        try:
            int(end)
        except (ValueError, TypeError) as exc:
            raise ProximoError(
                f"invalid end: {end!r} (must be an integer Unix epoch)"
            ) from exc
    params: dict = {"quarantine-type": quarantine_type}
    if start is not None:
        params["starttime"] = int(start)
    if end is not None:
        params["endtime"] = int(end)
    return api._get("/quarantine/spamusers", params=params) or []


def statistics_mailcount(
    api: PmgBackend,
    start: int | None = None,
    end: int | None = None,
    timespan: int = 3600,
) -> list[dict]:
    """Get per-bucket mail count statistics.

    GET /statistics/mailcount

    PMG 9.1 live-verified path via pmgsh ls.
    timespan: histogram bucket size in seconds, 3600–31622400 (default 3600 = 1 hour).
    Maps start/end epoch params → starttime/endtime query params.
    """
    try:
        timespan_int = int(timespan)
    except (ValueError, TypeError) as exc:
        raise ProximoError(
            f"invalid timespan: {timespan!r} — must be an integer"
        ) from exc
    if not (3600 <= timespan_int <= 31622400):
        raise ProximoError(
            f"invalid timespan: {timespan!r} — must be in range 3600–31622400"
        )
    if start is not None:
        try:
            int(start)
        except (ValueError, TypeError) as exc:
            raise ProximoError(
                f"invalid start: {start!r} (must be an integer Unix epoch)"
            ) from exc
    if end is not None:
        try:
            int(end)
        except (ValueError, TypeError) as exc:
            raise ProximoError(
                f"invalid end: {end!r} (must be an integer Unix epoch)"
            ) from exc
    params: dict = {"timespan": timespan_int}
    if start is not None:
        params["starttime"] = int(start)
    if end is not None:
        params["endtime"] = int(end)
    return api._get("/statistics/mailcount", params=params) or []


def statistics_sender(
    api: PmgBackend,
    start: int | None = None,
    end: int | None = None,
    filter_: str | None = None,
    orderby: str | None = None,
) -> list[dict]:
    """Get per-sender mail statistics.

    GET /statistics/sender

    PMG 9.1 live-verified path via pmgsh ls.
    filter_: optional search string (maps to API param 'filter').
    orderby: accepted for API compatibility but SILENTLY IGNORED.
             PMG 9.1 live-verified: /statistics/sender does not have an 'orderby'
             parameter; passing it causes HTTP 400 'Parameter verification failed.'
    Maps start/end epoch params → starttime/endtime query params.
    """
    if start is not None:
        try:
            int(start)
        except (ValueError, TypeError) as exc:
            raise ProximoError(
                f"invalid start: {start!r} (must be an integer Unix epoch)"
            ) from exc
    if end is not None:
        try:
            int(end)
        except (ValueError, TypeError) as exc:
            raise ProximoError(
                f"invalid end: {end!r} (must be an integer Unix epoch)"
            ) from exc
    params: dict = {}
    if start is not None:
        params["starttime"] = int(start)
    if end is not None:
        params["endtime"] = int(end)
    if filter_ is not None:
        params["filter"] = filter_
    # orderby is NOT sent to PMG — /statistics/sender rejects it with HTTP 400.
    # Accepted as a parameter so callers with older Proximo integrations don't break.
    return api._get("/statistics/sender", params=params if params else None) or []


def statistics_receiver(
    api: PmgBackend,
    start: int | None = None,
    end: int | None = None,
    filter_: str | None = None,
    orderby: str | None = None,
) -> list[dict]:
    """Get per-recipient mail statistics.

    GET /statistics/receiver

    PMG 9.1 live-verified path via pmgsh ls.
    filter_: optional search string (maps to API param 'filter').
    orderby: optional sort spec — raw passthrough, no validation.
    Maps start/end epoch params → starttime/endtime query params.
    """
    if start is not None:
        try:
            int(start)
        except (ValueError, TypeError) as exc:
            raise ProximoError(
                f"invalid start: {start!r} (must be an integer Unix epoch)"
            ) from exc
    if end is not None:
        try:
            int(end)
        except (ValueError, TypeError) as exc:
            raise ProximoError(
                f"invalid end: {end!r} (must be an integer Unix epoch)"
            ) from exc
    params: dict = {}
    if start is not None:
        params["starttime"] = int(start)
    if end is not None:
        params["endtime"] = int(end)
    if filter_ is not None:
        params["filter"] = filter_
    if orderby is not None:
        params["orderby"] = orderby
    return api._get("/statistics/receiver", params=params if params else None) or []


def node_syslog(
    api: PmgBackend,
    node: str,
    limit: int | None = None,
    service: str | None = None,
    since: str | None = None,
    until: str | None = None,
    start: int | None = None,
) -> list[dict]:
    """Get PMG node syslog entries.

    GET /nodes/{node}/syslog

    PMG 9.1 live-verified path via pmgsh ls.
    limit: max entries to return.
    service: filter by systemd service name.
    since/until: time range (syslog timestamp format or epoch).
    start: pagination offset (record index).
    """
    node = _check_node(node)
    params: dict = {}
    if limit is not None:
        params["limit"] = int(limit)
    if service is not None:
        params["service"] = service
    if since is not None:
        params["since"] = since
    if until is not None:
        params["until"] = until
    if start is not None:
        params["start"] = int(start)
    return api._get(f"/nodes/{node}/syslog", params=params if params else None) or []


def node_rrddata(
    api: PmgBackend,
    node: str,
    timeframe: str,
    cf: str | None = None,
) -> list[dict]:
    """Get PMG node RRD performance data.

    GET /nodes/{node}/rrddata

    PMG 9.1 live-verified path via pmgsh ls.
    timeframe: REQUIRED — hour|day|week|month|year.
    cf: consolidation function AVERAGE|MAX (optional).
    """
    node = _check_node(node)
    timeframe = _check_rrddata_timeframe(timeframe)
    params: dict = {"timeframe": timeframe}
    if cf is not None:
        cf = _check_rrddata_cf(cf)
        params["cf"] = cf
    return api._get(f"/nodes/{node}/rrddata", params=params) or []


def tasks_list(
    api: PmgBackend,
    node: str,
    start: int | None = None,
    limit: int | None = None,
    userfilter: str | None = None,
    errors: bool | None = None,
    typefilter: str | None = None,
    since: int | None = None,
    until: int | None = None,
    statusfilter: str | None = None,
) -> list[dict]:
    """List PMG tasks on a node.

    GET /nodes/{node}/tasks

    PMG 9.1 live-verified path via pmgsh ls.
    start: pagination offset; limit: max entries.
    errors: if True, return only failed tasks.
    """
    node = _check_node(node)
    params: dict = {}
    if start is not None:
        params["start"] = int(start)
    if limit is not None:
        params["limit"] = int(limit)
    if userfilter is not None:
        params["userfilter"] = userfilter
    if errors is not None:
        params["errors"] = 1 if errors else 0
    if typefilter is not None:
        params["typefilter"] = typefilter
    if since is not None:
        params["since"] = int(since)
    if until is not None:
        params["until"] = int(until)
    if statusfilter is not None:
        params["statusfilter"] = statusfilter
    return api._get(f"/nodes/{node}/tasks", params=params if params else None) or []


# ---------------------------------------------------------------------------
# W4 MUTATION operations
# ---------------------------------------------------------------------------


def backup_create(
    api: PmgBackend,
    node: str,
    notify: str = "never",
    statistic: bool = True,
) -> object:
    """Create a PMG configuration backup.

    POST /nodes/{node}/backup

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 live-verified path via pmgsh ls.
    notify: always|error|never (default never).
    statistic: include mail statistics in backup (default True).
    Backup file is written to /var/lib/pmg/backup/ on the target node.
    """
    node = _check_node(node)
    notify = _check_backup_notify(notify)
    body: dict = {"notify": notify, "statistic": statistic}
    return api._post(f"/nodes/{node}/backup", data=body)


# ---------------------------------------------------------------------------
# W4 PLAN functions
# ---------------------------------------------------------------------------


def plan_backup_create(
    node: str,
    notify: str = "never",
    statistic: bool = True,
) -> Plan:
    """Preview creating a PMG configuration backup.  PURE — no API call.

    RISK_LOW: additive — writes a new backup .tar.gz to /var/lib/pmg/backup/.
    No existing backups or configuration data is deleted.
    """
    node = _check_node(node)
    notify = _check_backup_notify(notify)
    return Plan(
        action="pmg_backup_create",
        target=f"pmg/{node}/backup",
        change=f"create PMG configuration backup on node '{node}'",
        current={},
        blast_radius=[
            f"writes a backup .tar.gz to /var/lib/pmg/backup/ on node '{node}'",
            "additive: creates a new backup file; no existing backups or config deleted",
            f"notify: '{notify}' — "
            f"{'always' if notify == 'always' else 'on error only' if notify == 'error' else 'never'}",
            f"statistic: {'included' if statistic else 'excluded'} from backup",
        ],
        risk=RISK_LOW,
        risk_reasons=[
            "additive: writes one new backup .tar.gz file; no live service is stopped",
            "LOW: backup reads current config and writes an archive; no state is deleted",
        ],
        note="PMG 9.1 live-verified path via pmgsh ls: POST /nodes/{node}/backup.",
    )


# ---------------------------------------------------------------------------
# W5a Validators
# ---------------------------------------------------------------------------

# RuleDB rule ID: PMG ruledb uses positive integer IDs as URL path segments.
# Reject any non-digit content (slashes, dots, control chars) to block traversal.
_RULEDB_ID_RE = re.compile(r"^\d+\Z")


def _check_ruledb_id(id_: str) -> str:
    # Do NOT strip — \Z must catch trailing newlines.
    s = str(id_)
    if not _RULEDB_ID_RE.match(s):
        raise ProximoError(
            f"invalid ruledb rule ID: {id_!r} "
            "(must be a positive integer string, e.g. '100'; no slashes or control chars)"
        )
    return s


# Object group name: used as a URL path segment in /config/ruledb/who|what|when/{ogroup}/...
# Allows alphanumeric + hyphen + underscore; starts with alnum; ≤64 chars.
_OGROUP_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")


def _check_ogroup(ogroup: str) -> str:
    # Do NOT strip — \Z must catch trailing newlines.
    s = str(ogroup)
    if not _OGROUP_RE.match(s):
        raise ProximoError(
            f"invalid object group name: {ogroup!r} "
            "(must start with alnum, then alnum/hyphen/underscore, "
            "≤64 chars, no slashes or control chars)"
        )
    return s


# ---------------------------------------------------------------------------
# W5a READ operations — RuleDB filtering engine inventory/observability
# ---------------------------------------------------------------------------


def ruledb_rules_list(api: PmgBackend) -> list[dict]:
    """List all PMG RuleDB rules (hydrated rule list).

    GET /config/ruledb/rules

    PMG 9.1 pmgsh-verified path.
    Returns the full hydrated rule list including from/to/what/when/actions.
    """
    return api._get("/config/ruledb/rules") or []


def ruledb_rule_get(api: PmgBackend, id_: str) -> dict:
    """Get a PMG RuleDB rule's configuration.

    GET /config/ruledb/rules/{id}/config

    PMG 9.1 pmgsh-verified path.
    id_: rule ID (positive integer string, e.g. '100').
    """
    id_ = _check_ruledb_id(id_)
    return api._get(f"/config/ruledb/rules/{id_}/config") or {}


def ruledb_rule_from_list(api: PmgBackend, id_: str) -> list[dict]:
    """List the 'from' objects attached to a PMG RuleDB rule.

    GET /config/ruledb/rules/{id}/from

    PMG 9.1 pmgsh-verified path.
    id_: rule ID (positive integer string, e.g. '100').
    """
    id_ = _check_ruledb_id(id_)
    return api._get(f"/config/ruledb/rules/{id_}/from") or []


def ruledb_rule_to_list(api: PmgBackend, id_: str) -> list[dict]:
    """List the 'to' objects attached to a PMG RuleDB rule.

    GET /config/ruledb/rules/{id}/to

    PMG 9.1 pmgsh-verified path.
    id_: rule ID (positive integer string, e.g. '100').
    """
    id_ = _check_ruledb_id(id_)
    return api._get(f"/config/ruledb/rules/{id_}/to") or []


def ruledb_rule_what_list(api: PmgBackend, id_: str) -> list[dict]:
    """List the 'what' objects attached to a PMG RuleDB rule.

    GET /config/ruledb/rules/{id}/what

    PMG 9.1 pmgsh-verified path.
    id_: rule ID (positive integer string, e.g. '100').
    """
    id_ = _check_ruledb_id(id_)
    return api._get(f"/config/ruledb/rules/{id_}/what") or []


def ruledb_rule_when_list(api: PmgBackend, id_: str) -> list[dict]:
    """List the 'when' objects attached to a PMG RuleDB rule.

    GET /config/ruledb/rules/{id}/when

    PMG 9.1 pmgsh-verified path.
    id_: rule ID (positive integer string, e.g. '100').
    """
    id_ = _check_ruledb_id(id_)
    return api._get(f"/config/ruledb/rules/{id_}/when") or []


def ruledb_rule_actions_list(api: PmgBackend, id_: str) -> list[dict]:
    """List the 'actions' objects attached to a PMG RuleDB rule.

    GET /config/ruledb/rules/{id}/config  (extracts the 'action' field)

    PMG 9.1 live-verified: GET /config/ruledb/rules/{id}/actions returns 501
    (not implemented). The actions list is embedded in the rule config response
    under the 'action' key. This function calls the config endpoint and returns
    that embedded list so callers get a consistent list-of-dicts interface.
    id_: rule ID (positive integer string, e.g. '100').
    """
    id_ = _check_ruledb_id(id_)
    cfg = api._get(f"/config/ruledb/rules/{id_}/config") or {}
    return cfg.get("action") or []


def who_groups_list(api: PmgBackend) -> list[dict]:
    """List all PMG RuleDB 'who' object groups.

    GET /config/ruledb/who

    PMG 9.1 pmgsh-verified path.
    """
    return api._get("/config/ruledb/who") or []


def who_group_get(api: PmgBackend, ogroup: str) -> dict:
    """Get a PMG RuleDB 'who' object group's configuration.

    GET /config/ruledb/who/{ogroup}/config

    PMG 9.1 live-verified: ogroup must be the numeric ID string from
    who_groups_list (e.g. '2'), NOT the group name (e.g. 'Blocklist').
    Passing a name causes PMG to return HTTP 400 Parameter verification failed.
    ogroup: numeric ID string (e.g. '2') from who_groups_list response.
    """
    ogroup = _check_ruledb_id(ogroup)
    return api._get(f"/config/ruledb/who/{ogroup}/config") or {}


def who_group_objects(api: PmgBackend, ogroup: str) -> list[dict]:
    """List the objects in a PMG RuleDB 'who' object group.

    GET /config/ruledb/who/{ogroup}/objects

    PMG 9.1 live-verified: ogroup must be the numeric ID string from
    who_groups_list (e.g. '2'), NOT the group name (e.g. 'Blocklist').
    ogroup: numeric ID string (e.g. '2') from who_groups_list response.
    """
    ogroup = _check_ruledb_id(ogroup)
    return api._get(f"/config/ruledb/who/{ogroup}/objects") or []


def what_groups_list(api: PmgBackend) -> list[dict]:
    """List all PMG RuleDB 'what' object groups.

    GET /config/ruledb/what

    PMG 9.1 pmgsh-verified path.
    """
    return api._get("/config/ruledb/what") or []


def what_group_get(api: PmgBackend, ogroup: str) -> dict:
    """Get a PMG RuleDB 'what' object group's configuration.

    GET /config/ruledb/what/{ogroup}/config

    PMG 9.1 live-verified: ogroup must be the numeric ID string from
    what_groups_list (e.g. '8'), NOT the group name (e.g. 'DangerousContent').
    Passing a name causes PMG to return HTTP 400 Parameter verification failed.
    ogroup: numeric ID string (e.g. '8') from what_groups_list response.
    """
    ogroup = _check_ruledb_id(ogroup)
    return api._get(f"/config/ruledb/what/{ogroup}/config") or {}


def what_group_objects(api: PmgBackend, ogroup: str) -> list[dict]:
    """List the objects in a PMG RuleDB 'what' object group.

    GET /config/ruledb/what/{ogroup}/objects

    PMG 9.1 live-verified: ogroup must be the numeric ID string from
    what_groups_list (e.g. '8'), NOT the group name.
    ogroup: numeric ID string (e.g. '8') from what_groups_list response.
    """
    ogroup = _check_ruledb_id(ogroup)
    return api._get(f"/config/ruledb/what/{ogroup}/objects") or []


def when_groups_list(api: PmgBackend) -> list[dict]:
    """List all PMG RuleDB 'when' object groups.

    GET /config/ruledb/when

    PMG 9.1 pmgsh-verified path.
    """
    return api._get("/config/ruledb/when") or []


def when_group_get(api: PmgBackend, ogroup: str) -> dict:
    """Get a PMG RuleDB 'when' object group's configuration.

    GET /config/ruledb/when/{ogroup}/config

    PMG 9.1 live-verified: ogroup must be the numeric ID string from
    when_groups_list (e.g. '4'), NOT the group name (e.g. 'OfficeHours').
    Passing a name causes PMG to return HTTP 400 Parameter verification failed.
    ogroup: numeric ID string (e.g. '4') from when_groups_list response.
    """
    ogroup = _check_ruledb_id(ogroup)
    return api._get(f"/config/ruledb/when/{ogroup}/config") or {}


def when_group_objects(api: PmgBackend, ogroup: str) -> list[dict]:
    """List the objects in a PMG RuleDB 'when' object group.

    GET /config/ruledb/when/{ogroup}/objects

    PMG 9.1 live-verified: ogroup must be the numeric ID string from
    when_groups_list (e.g. '4'), NOT the group name.
    ogroup: numeric ID string (e.g. '4') from when_groups_list response.
    """
    ogroup = _check_ruledb_id(ogroup)
    return api._get(f"/config/ruledb/when/{ogroup}/objects") or []


def action_objects_list(api: PmgBackend) -> list[dict]:
    """List all PMG RuleDB action objects (including non-editable).

    GET /config/ruledb/action/objects

    PMG 9.1 pmgsh-verified path.
    Returns all action objects; each entry carries an 'editable' flag.
    Non-editable action objects are built-in and cannot be modified via the API.
    """
    return api._get("/config/ruledb/action/objects") or []


def ruledb_digest(api: PmgBackend) -> dict:
    """Get the PMG RuleDB digest (change-detection hash).

    GET /config/ruledb/digest

    PMG 9.1 pmgsh-verified path.
    The digest changes whenever any ruledb configuration is modified.
    Use to detect configuration drift without fetching the full rule list.
    """
    return api._get("/config/ruledb/digest") or {}


# ---------------------------------------------------------------------------
# W5b Validators
# ---------------------------------------------------------------------------

# WHO object type enum: type controls the sub-path for object CRUD.
_WHO_OBJECT_TYPES = frozenset({"email", "domain", "regex", "ip", "network", "ldap"})


def _check_who_object_type(type_: str) -> str:
    if type_ not in _WHO_OBJECT_TYPES:
        raise ProximoError(
            f"invalid who-object type: {type_!r}. "
            f"Must be one of: {', '.join(sorted(_WHO_OBJECT_TYPES))}"
        )
    return type_


# ---------------------------------------------------------------------------
# W5b MUTATION operations — object-group CRUD + who-object CRUD
# ---------------------------------------------------------------------------


def who_group_create(
    api: PmgBackend,
    name: str,
    info: str | None = None,
    and_: bool | None = None,
    invert: bool | None = None,
) -> object:
    """Create a PMG RuleDB 'who' object group.

    POST /config/ruledb/who

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 pmgsh-verified path.
    name: group name.
    info: optional description.
    and_: Python alias for the API param 'and' (bool; AND vs OR logic for group members).
    invert: if True, the group match is inverted.
    Returns the numeric ogroup ID assigned by PMG.
    """
    body: dict = {"name": name}
    if info is not None:
        body["info"] = info
    if and_ is not None:
        body["and"] = and_
    if invert is not None:
        body["invert"] = invert
    return api._post("/config/ruledb/who", data=body)


def who_group_update(
    api: PmgBackend,
    ogroup: str,
    name: str | None = None,
    info: str | None = None,
    and_: bool | None = None,
    invert: bool | None = None,
) -> object:
    """Update a PMG RuleDB 'who' object group's configuration.

    PUT /config/ruledb/who/{ogroup}/config

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 pmgsh-verified path.
    ogroup: numeric ID string (e.g. '2') from who_groups_list response.
    Only non-None fields are sent; omitted fields keep their current values.
    """
    ogroup = _check_ruledb_id(ogroup)
    body: dict = {}
    if name is not None:
        body["name"] = name
    if info is not None:
        body["info"] = info
    if and_ is not None:
        body["and"] = and_
    if invert is not None:
        body["invert"] = invert
    return api._put(f"/config/ruledb/who/{ogroup}/config", data=body)


def who_group_delete(api: PmgBackend, ogroup: str) -> object:
    """Delete a PMG RuleDB 'who' object group.

    DELETE /config/ruledb/who/{ogroup}

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 pmgsh-verified path.
    ogroup: numeric ID string (e.g. '2') from who_groups_list response.
    WARNING: also removes all objects within the group.
    """
    ogroup = _check_ruledb_id(ogroup)
    return api._delete(f"/config/ruledb/who/{ogroup}")


def what_group_create(
    api: PmgBackend,
    name: str,
    info: str | None = None,
    and_: bool | None = None,
    invert: bool | None = None,
) -> object:
    """Create a PMG RuleDB 'what' object group.

    POST /config/ruledb/what

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 pmgsh-verified path.
    name: group name.
    info: optional description.
    and_: Python alias for the API param 'and' (bool; AND vs OR logic for group members).
    invert: if True, the group match is inverted.
    Returns the numeric ogroup ID assigned by PMG.
    """
    body: dict = {"name": name}
    if info is not None:
        body["info"] = info
    if and_ is not None:
        body["and"] = and_
    if invert is not None:
        body["invert"] = invert
    return api._post("/config/ruledb/what", data=body)


def what_group_update(
    api: PmgBackend,
    ogroup: str,
    name: str | None = None,
    info: str | None = None,
    and_: bool | None = None,
    invert: bool | None = None,
) -> object:
    """Update a PMG RuleDB 'what' object group's configuration.

    PUT /config/ruledb/what/{ogroup}/config

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 pmgsh-verified path.
    ogroup: numeric ID string (e.g. '8') from what_groups_list response.
    Only non-None fields are sent; omitted fields keep their current values.
    """
    ogroup = _check_ruledb_id(ogroup)
    body: dict = {}
    if name is not None:
        body["name"] = name
    if info is not None:
        body["info"] = info
    if and_ is not None:
        body["and"] = and_
    if invert is not None:
        body["invert"] = invert
    return api._put(f"/config/ruledb/what/{ogroup}/config", data=body)


def what_group_delete(api: PmgBackend, ogroup: str) -> object:
    """Delete a PMG RuleDB 'what' object group.

    DELETE /config/ruledb/what/{ogroup}

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 pmgsh-verified path.
    ogroup: numeric ID string (e.g. '8') from what_groups_list response.
    WARNING: also removes all objects within the group.
    """
    ogroup = _check_ruledb_id(ogroup)
    return api._delete(f"/config/ruledb/what/{ogroup}")


def when_group_create(
    api: PmgBackend,
    name: str,
    info: str | None = None,
    and_: bool | None = None,
    invert: bool | None = None,
) -> object:
    """Create a PMG RuleDB 'when' object group.

    POST /config/ruledb/when

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 pmgsh-verified path.
    name: group name.
    info: optional description.
    and_: Python alias for the API param 'and' (bool; AND vs OR logic for group members).
    invert: if True, the group match is inverted.
    Returns the numeric ogroup ID assigned by PMG.
    """
    body: dict = {"name": name}
    if info is not None:
        body["info"] = info
    if and_ is not None:
        body["and"] = and_
    if invert is not None:
        body["invert"] = invert
    return api._post("/config/ruledb/when", data=body)


def when_group_update(
    api: PmgBackend,
    ogroup: str,
    name: str | None = None,
    info: str | None = None,
    and_: bool | None = None,
    invert: bool | None = None,
) -> object:
    """Update a PMG RuleDB 'when' object group's configuration.

    PUT /config/ruledb/when/{ogroup}/config

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 pmgsh-verified path.
    ogroup: numeric ID string (e.g. '4') from when_groups_list response.
    Only non-None fields are sent; omitted fields keep their current values.
    """
    ogroup = _check_ruledb_id(ogroup)
    body: dict = {}
    if name is not None:
        body["name"] = name
    if info is not None:
        body["info"] = info
    if and_ is not None:
        body["and"] = and_
    if invert is not None:
        body["invert"] = invert
    return api._put(f"/config/ruledb/when/{ogroup}/config", data=body)


def when_group_delete(api: PmgBackend, ogroup: str) -> object:
    """Delete a PMG RuleDB 'when' object group.

    DELETE /config/ruledb/when/{ogroup}

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 pmgsh-verified path.
    ogroup: numeric ID string (e.g. '4') from when_groups_list response.
    WARNING: also removes all objects within the group.
    """
    ogroup = _check_ruledb_id(ogroup)
    return api._delete(f"/config/ruledb/when/{ogroup}")


def who_object_add(
    api: PmgBackend,
    ogroup: str,
    type_: str,
    *,
    email: str | None = None,
    domain: str | None = None,
    regex: str | None = None,
    ip: str | None = None,
    cidr: str | None = None,
    mode: str | None = None,
    profile: str | None = None,
    group: str | None = None,
) -> object:
    """Add an object to a PMG RuleDB 'who' object group.

    POST /config/ruledb/who/{ogroup}/{type}

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 pmgsh-verified path.
    ogroup: numeric ID string (e.g. '2') from who_groups_list response.
    type_: email|domain|regex|ip|network|ldap — controls the sub-path.
    Type-specific fields (send only relevant non-None fields):
        email:   email (str)
        domain:  domain (str)
        regex:   regex (str)
        ip:      ip (str)
        network: cidr (str)
        ldap:    mode (any|none|group), profile (str), group (str)
    NOTE: if the group is already bound to a rule, the new object affects
    mail matching immediately on add.
    """
    ogroup = _check_ruledb_id(ogroup)
    type_ = _check_who_object_type(type_)
    body: dict = {}
    if type_ == "email":
        if email is not None:
            body["email"] = email
    elif type_ == "domain":
        if domain is not None:
            body["domain"] = domain
    elif type_ == "regex":
        if regex is not None:
            body["regex"] = regex
    elif type_ == "ip":
        if ip is not None:
            body["ip"] = ip
    elif type_ == "network":
        if cidr is not None:
            body["cidr"] = cidr
    elif type_ == "ldap":
        if mode is not None:
            body["mode"] = mode
        if profile is not None:
            body["profile"] = profile
        if group is not None:
            body["group"] = group
    return api._post(f"/config/ruledb/who/{ogroup}/{type_}", data=body)


def who_object_update(
    api: PmgBackend,
    ogroup: str,
    type_: str,
    id_: str,
    *,
    email: str | None = None,
    domain: str | None = None,
    regex: str | None = None,
    ip: str | None = None,
    cidr: str | None = None,
    mode: str | None = None,
    profile: str | None = None,
    group: str | None = None,
) -> object:
    """Update an object in a PMG RuleDB 'who' object group.

    PUT /config/ruledb/who/{ogroup}/{type}/{id}

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 pmgsh-verified path.
    ogroup: numeric ID string (e.g. '2') from who_groups_list response.
    type_: email|domain|regex|ip|network|ldap — controls the sub-path.
    id_: object ID (numeric string) from who_group_objects response.
    All type-specific fields are optional; only non-None fields are sent.
    """
    ogroup = _check_ruledb_id(ogroup)
    type_ = _check_who_object_type(type_)
    id_ = _check_ruledb_id(id_)
    body: dict = {}
    if type_ == "email":
        if email is not None:
            body["email"] = email
    elif type_ == "domain":
        if domain is not None:
            body["domain"] = domain
    elif type_ == "regex":
        if regex is not None:
            body["regex"] = regex
    elif type_ == "ip":
        if ip is not None:
            body["ip"] = ip
    elif type_ == "network":
        if cidr is not None:
            body["cidr"] = cidr
    elif type_ == "ldap":
        if mode is not None:
            body["mode"] = mode
        if profile is not None:
            body["profile"] = profile
        if group is not None:
            body["group"] = group
    return api._put(f"/config/ruledb/who/{ogroup}/{type_}/{id_}", data=body)


def who_object_delete(api: PmgBackend, ogroup: str, id_: str) -> object:
    """Delete an object from a PMG RuleDB 'who' object group.

    DELETE /config/ruledb/who/{ogroup}/objects/{id}

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 pmgsh-verified path.
    ogroup: numeric ID string (e.g. '2') from who_groups_list response.
    id_: object ID (numeric string) from who_group_objects response.
    Object DELETE always goes through /objects/{id} regardless of type.
    """
    ogroup = _check_ruledb_id(ogroup)
    id_ = _check_ruledb_id(id_)
    return api._delete(f"/config/ruledb/who/{ogroup}/objects/{id_}")


# ---------------------------------------------------------------------------
# W5b PLAN functions — object-group CRUD + who-object CRUD (PURE — no API call)
# ---------------------------------------------------------------------------


def plan_who_group_create(
    name: str,
    info: str | None = None,
    and_: bool | None = None,
    invert: bool | None = None,
) -> Plan:
    """Preview creating a PMG RuleDB 'who' object group.  PURE — no API call.

    RISK_LOW: additive — creates an empty group; affects no mail until attached
    to a rule (W5d).
    """
    return Plan(
        action="pmg_who_group_create",
        target="config/ruledb/who",
        change=f"create 'who' object group '{name}'",
        current={},
        blast_radius=[
            f"creates an empty 'who' object group named '{name}'",
            "additive: does not affect existing groups, objects, or mail flow",
            "the group has no effect until attached to a rule (W5d)",
        ],
        risk=RISK_LOW,
        risk_reasons=[
            "additive: creates one empty group; no existing config or mail deleted",
            "LOW: group is inactive until bound to a rule",
        ],
        note="PMG 9.1 pmgsh-verified path: POST /config/ruledb/who.",
    )


def plan_who_group_update(
    ogroup: str,
    name: str | None = None,
    info: str | None = None,
    and_: bool | None = None,
    invert: bool | None = None,
) -> Plan:
    """Preview updating a PMG RuleDB 'who' object group's configuration.  PURE — no API call.

    RISK_MEDIUM: modifies an existing group; if bound to a rule, the change
    affects mail matching immediately.
    """
    ogroup = _check_ruledb_id(ogroup)
    return Plan(
        action="pmg_who_group_update",
        target=f"config/ruledb/who/{ogroup}/config",
        change=f"update 'who' object group {ogroup} config",
        current={},
        blast_radius=[
            f"modifies the configuration of 'who' group {ogroup}",
            "if the group is bound to an active rule, matching changes take effect immediately",
            "review all rules referencing this group before confirming",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=[
            "MEDIUM: modifies an existing group; active rules referencing it are affected",
            "logic changes (and/invert) can flip rule matching for live mail",
        ],
        note="PMG 9.1 pmgsh-verified path: PUT /config/ruledb/who/{ogroup}/config.",
    )


def plan_who_group_delete(ogroup: str) -> Plan:
    """Preview deleting a PMG RuleDB 'who' object group.  PURE — no API call.

    RISK_MEDIUM: removes the group and all its objects; rules referencing it
    may break.
    """
    ogroup = _check_ruledb_id(ogroup)
    return Plan(
        action="pmg_who_group_delete",
        target=f"config/ruledb/who/{ogroup}",
        change=f"delete 'who' object group {ogroup}",
        current={},
        blast_radius=[
            f"permanently removes 'who' group {ogroup} and all its objects",
            "rules that reference this group will lose their 'from' match condition",
            "affected rules may start matching all senders or become invalid",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=[
            "MEDIUM: deletes a group and all contained objects; cannot be undone without re-creating",
            "rules referencing the deleted group may mismatch or fail",
        ],
        note="PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/who/{ogroup}.",
    )


def plan_what_group_create(
    name: str,
    info: str | None = None,
    and_: bool | None = None,
    invert: bool | None = None,
) -> Plan:
    """Preview creating a PMG RuleDB 'what' object group.  PURE — no API call.

    RISK_LOW: additive — creates an empty group; affects no mail until attached
    to a rule (W5d).
    """
    return Plan(
        action="pmg_what_group_create",
        target="config/ruledb/what",
        change=f"create 'what' object group '{name}'",
        current={},
        blast_radius=[
            f"creates an empty 'what' object group named '{name}'",
            "additive: does not affect existing groups, objects, or mail flow",
            "the group has no effect until attached to a rule (W5d)",
        ],
        risk=RISK_LOW,
        risk_reasons=[
            "additive: creates one empty group; no existing config or mail deleted",
            "LOW: group is inactive until bound to a rule",
        ],
        note="PMG 9.1 pmgsh-verified path: POST /config/ruledb/what.",
    )


def plan_what_group_update(
    ogroup: str,
    name: str | None = None,
    info: str | None = None,
    and_: bool | None = None,
    invert: bool | None = None,
) -> Plan:
    """Preview updating a PMG RuleDB 'what' object group's configuration.  PURE — no API call.

    RISK_MEDIUM: modifies an existing group; if bound to a rule, the change
    affects mail matching immediately.
    """
    ogroup = _check_ruledb_id(ogroup)
    return Plan(
        action="pmg_what_group_update",
        target=f"config/ruledb/what/{ogroup}/config",
        change=f"update 'what' object group {ogroup} config",
        current={},
        blast_radius=[
            f"modifies the configuration of 'what' group {ogroup}",
            "if the group is bound to an active rule, matching changes take effect immediately",
            "review all rules referencing this group before confirming",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=[
            "MEDIUM: modifies an existing group; active rules referencing it are affected",
            "logic changes (and/invert) can flip rule matching for live mail",
        ],
        note="PMG 9.1 pmgsh-verified path: PUT /config/ruledb/what/{ogroup}/config.",
    )


def plan_what_group_delete(ogroup: str) -> Plan:
    """Preview deleting a PMG RuleDB 'what' object group.  PURE — no API call.

    RISK_MEDIUM: removes the group and all its objects; rules referencing it
    may break.
    """
    ogroup = _check_ruledb_id(ogroup)
    return Plan(
        action="pmg_what_group_delete",
        target=f"config/ruledb/what/{ogroup}",
        change=f"delete 'what' object group {ogroup}",
        current={},
        blast_radius=[
            f"permanently removes 'what' group {ogroup} and all its objects",
            "rules that reference this group will lose their 'what' match condition",
            "affected rules may start matching all content or become invalid",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=[
            "MEDIUM: deletes a group and all contained objects; cannot be undone without re-creating",
            "rules referencing the deleted group may mismatch or fail",
        ],
        note="PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/what/{ogroup}.",
    )


def plan_when_group_create(
    name: str,
    info: str | None = None,
    and_: bool | None = None,
    invert: bool | None = None,
) -> Plan:
    """Preview creating a PMG RuleDB 'when' object group.  PURE — no API call.

    RISK_LOW: additive — creates an empty group; affects no mail until attached
    to a rule (W5d).
    """
    return Plan(
        action="pmg_when_group_create",
        target="config/ruledb/when",
        change=f"create 'when' object group '{name}'",
        current={},
        blast_radius=[
            f"creates an empty 'when' object group named '{name}'",
            "additive: does not affect existing groups, objects, or mail flow",
            "the group has no effect until attached to a rule (W5d)",
        ],
        risk=RISK_LOW,
        risk_reasons=[
            "additive: creates one empty group; no existing config or mail deleted",
            "LOW: group is inactive until bound to a rule",
        ],
        note="PMG 9.1 pmgsh-verified path: POST /config/ruledb/when.",
    )


def plan_when_group_update(
    ogroup: str,
    name: str | None = None,
    info: str | None = None,
    and_: bool | None = None,
    invert: bool | None = None,
) -> Plan:
    """Preview updating a PMG RuleDB 'when' object group's configuration.  PURE — no API call.

    RISK_MEDIUM: modifies an existing group; if bound to a rule, the change
    affects mail matching immediately.
    """
    ogroup = _check_ruledb_id(ogroup)
    return Plan(
        action="pmg_when_group_update",
        target=f"config/ruledb/when/{ogroup}/config",
        change=f"update 'when' object group {ogroup} config",
        current={},
        blast_radius=[
            f"modifies the configuration of 'when' group {ogroup}",
            "if the group is bound to an active rule, matching changes take effect immediately",
            "review all rules referencing this group before confirming",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=[
            "MEDIUM: modifies an existing group; active rules referencing it are affected",
            "logic changes (and/invert) can flip rule matching for live mail",
        ],
        note="PMG 9.1 pmgsh-verified path: PUT /config/ruledb/when/{ogroup}/config.",
    )


def plan_when_group_delete(ogroup: str) -> Plan:
    """Preview deleting a PMG RuleDB 'when' object group.  PURE — no API call.

    RISK_MEDIUM: removes the group and all its objects; rules referencing it
    may break.
    """
    ogroup = _check_ruledb_id(ogroup)
    return Plan(
        action="pmg_when_group_delete",
        target=f"config/ruledb/when/{ogroup}",
        change=f"delete 'when' object group {ogroup}",
        current={},
        blast_radius=[
            f"permanently removes 'when' group {ogroup} and all its objects",
            "rules that reference this group will lose their 'when' match condition",
            "affected rules may match at all times or become invalid",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=[
            "MEDIUM: deletes a group and all contained objects; cannot be undone without re-creating",
            "rules referencing the deleted group may mismatch or fail",
        ],
        note="PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/when/{ogroup}.",
    )


def plan_who_object_add(
    ogroup: str,
    type_: str,
    *,
    email: str | None = None,
    domain: str | None = None,
    regex: str | None = None,
    ip: str | None = None,
    cidr: str | None = None,
    mode: str | None = None,
    profile: str | None = None,
    group: str | None = None,
) -> Plan:
    """Preview adding an object to a PMG RuleDB 'who' object group.  PURE — no API call.

    RISK_LOW: additive — adds one object to the group. NOTE: if the group is
    already bound to a rule, the new object affects mail matching immediately.
    """
    ogroup = _check_ruledb_id(ogroup)
    type_ = _check_who_object_type(type_)
    return Plan(
        action="pmg_who_object_add",
        target=f"config/ruledb/who/{ogroup}/{type_}",
        change=f"add {type_} object to 'who' group {ogroup}",
        current={},
        blast_radius=[
            f"adds one {type_} object to 'who' group {ogroup}",
            "additive: no existing objects are removed or modified",
            "WARNING: if group {ogroup} is already bound to a rule, the new object "
            "affects mail matching immediately on add",
        ],
        risk=RISK_LOW,
        risk_reasons=[
            "additive: adds one object; no existing config or mail deleted",
            "LOW overall — but immediate effect if group is in an active rule",
        ],
        note=f"PMG 9.1 pmgsh-verified path: POST /config/ruledb/who/{{ogroup}}/{type_}.",
    )


def plan_who_object_update(
    ogroup: str,
    type_: str,
    id_: str,
    *,
    email: str | None = None,
    domain: str | None = None,
    regex: str | None = None,
    ip: str | None = None,
    cidr: str | None = None,
    mode: str | None = None,
    profile: str | None = None,
    group: str | None = None,
) -> Plan:
    """Preview updating an object in a PMG RuleDB 'who' object group.  PURE — no API call.

    RISK_MEDIUM: modifies an existing object; if the group is bound to an active
    rule, the change affects mail matching immediately.
    """
    ogroup = _check_ruledb_id(ogroup)
    type_ = _check_who_object_type(type_)
    id_ = _check_ruledb_id(id_)
    return Plan(
        action="pmg_who_object_update",
        target=f"config/ruledb/who/{ogroup}/{type_}/{id_}",
        change=f"update {type_} object {id_} in 'who' group {ogroup}",
        current={},
        blast_radius=[
            f"modifies {type_} object {id_} in 'who' group {ogroup}",
            "if the group is bound to an active rule, the change takes effect immediately",
            "verify the new value matches your intended mail filter target",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=[
            "MEDIUM: modifies an existing object; active rules referencing the group are affected",
            "incorrect value could allow or block unintended mail immediately",
        ],
        note=f"PMG 9.1 pmgsh-verified path: PUT /config/ruledb/who/{{ogroup}}/{type_}/{{id}}.",
    )


def plan_who_object_delete(ogroup: str, id_: str) -> Plan:
    """Preview deleting an object from a PMG RuleDB 'who' object group.  PURE — no API call.

    RISK_MEDIUM: removes an existing object; if the group is bound to an active
    rule, the change affects mail matching immediately.
    """
    ogroup = _check_ruledb_id(ogroup)
    id_ = _check_ruledb_id(id_)
    return Plan(
        action="pmg_who_object_delete",
        target=f"config/ruledb/who/{ogroup}/objects/{id_}",
        change=f"delete object {id_} from 'who' group {ogroup}",
        current={},
        blast_radius=[
            f"permanently removes object {id_} from 'who' group {ogroup}",
            "if the group is bound to an active rule, the deletion takes effect immediately",
            "senders/addresses previously matched by this object will no longer match",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=[
            "MEDIUM: removes an existing object; cannot be undone without re-adding",
            "active rules referencing the group immediately lose this match entry",
        ],
        note="PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/who/{ogroup}/objects/{id}.",
    )


# ---------------------------------------------------------------------------
# W5c Validators
# ---------------------------------------------------------------------------

# WHAT object type enum: type controls the sub-path for what-object CRUD.
_WHAT_OBJECT_TYPES = frozenset({
    "contenttype",
    "matchfield",
    "spamfilter",
    "virusfilter",
    "filenamefilter",
    "archivefilter",
    "archivefilenamefilter",
})


def _check_what_object_type(type_: str) -> str:
    if type_ not in _WHAT_OBJECT_TYPES:
        raise ProximoError(
            f"invalid what-object type: {type_!r}. "
            f"Must be one of: {', '.join(sorted(_WHAT_OBJECT_TYPES))}"
        )
    return type_


# Disclaimer position enum.
_DISCLAIMER_POSITIONS = frozenset({"start", "end"})


def _check_action_position(position: str) -> str:
    if position not in _DISCLAIMER_POSITIONS:
        raise ProximoError(
            f"invalid disclaimer position: {position!r}. "
            f"Must be one of: {', '.join(sorted(_DISCLAIMER_POSITIONS))}"
        )
    return position


# Action object compound ID: format is {ogroup}_{objid} (e.g. '13_26').
# Both parts must be digit-only; reject traversal, control chars, and anything else.
_ACTION_OBJECT_ID_RE = re.compile(r"^\d+_\d+\Z")


def _check_action_object_id(id_: str) -> str:
    """Validate a compound action object ID (e.g. '13_26' = ogroup_objid)."""
    s = str(id_)
    if not _ACTION_OBJECT_ID_RE.match(s):
        raise ProximoError(
            f"invalid action object ID: {id_!r} "
            "(must be compound ogroup_objid format, e.g. '13_26')"
        )
    return s


# ---------------------------------------------------------------------------
# W5c MUTATION operations — WHAT-object CRUD
# ---------------------------------------------------------------------------


def what_object_add(
    api: PmgBackend,
    ogroup: str,
    type_: str,
    *,
    contenttype: str | None = None,
    only_content: bool | None = None,
    field: str | None = None,
    value: str | None = None,
    top_part_only: bool | None = None,
    spamlevel: int | None = None,
    filename: str | None = None,
) -> object:
    """Add an object to a PMG RuleDB 'what' object group.

    POST /config/ruledb/what/{ogroup}/{type}

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 pmgsh-verified path.
    ogroup: numeric ID string (e.g. '8') from what_groups_list response.
    type_: contenttype|matchfield|spamfilter|virusfilter|filenamefilter|
           archivefilter|archivefilenamefilter — controls the sub-path.
    Type-specific fields (send only relevant non-None fields):
        contenttype:           contenttype(str), only_content(bool → 'only-content')
        matchfield:            field(str), value(str), top_part_only(bool → 'top-part-only')
        spamfilter:            spamlevel(int)
        virusfilter:           (no type-specific fields; empty body)
        filenamefilter:        filename(str)
        archivefilter:         contenttype(str), only_content(bool → 'only-content')
        archivefilenamefilter: filename(str)
    NOTE: if the group is already bound to a rule, the new object affects
    mail matching immediately on add.
    """
    ogroup = _check_ruledb_id(ogroup)
    type_ = _check_what_object_type(type_)
    body: dict = {}
    if type_ in ("contenttype", "archivefilter"):
        if contenttype is not None:
            body["contenttype"] = contenttype
        if only_content is not None:
            body["only-content"] = only_content
    elif type_ == "matchfield":
        if field is not None:
            body["field"] = field
        if value is not None:
            body["value"] = value
        if top_part_only is not None:
            body["top-part-only"] = top_part_only
    elif type_ == "spamfilter":
        if spamlevel is not None:
            body["spamlevel"] = spamlevel
    elif type_ in ("filenamefilter", "archivefilenamefilter"):
        if filename is not None:
            body["filename"] = filename
    # virusfilter: empty body (no type-specific fields)
    return api._post(f"/config/ruledb/what/{ogroup}/{type_}", data=body)


def what_object_update(
    api: PmgBackend,
    ogroup: str,
    type_: str,
    id_: str,
    *,
    contenttype: str | None = None,
    only_content: bool | None = None,
    field: str | None = None,
    value: str | None = None,
    top_part_only: bool | None = None,
    spamlevel: int | None = None,
    filename: str | None = None,
) -> object:
    """Update an object in a PMG RuleDB 'what' object group.

    PUT /config/ruledb/what/{ogroup}/{type}/{id}

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 pmgsh-verified path.
    ogroup: numeric ID string (e.g. '8') from what_groups_list response.
    type_: contenttype|matchfield|spamfilter|virusfilter|filenamefilter|
           archivefilter|archivefilenamefilter — controls the sub-path.
    id_: object ID (numeric string) from what_group_objects response.
    All type-specific fields are optional; only non-None fields are sent.
    """
    ogroup = _check_ruledb_id(ogroup)
    type_ = _check_what_object_type(type_)
    id_ = _check_ruledb_id(id_)
    body: dict = {}
    if type_ in ("contenttype", "archivefilter"):
        if contenttype is not None:
            body["contenttype"] = contenttype
        if only_content is not None:
            body["only-content"] = only_content
    elif type_ == "matchfield":
        if field is not None:
            body["field"] = field
        if value is not None:
            body["value"] = value
        if top_part_only is not None:
            body["top-part-only"] = top_part_only
    elif type_ == "spamfilter":
        if spamlevel is not None:
            body["spamlevel"] = spamlevel
    elif type_ in ("filenamefilter", "archivefilenamefilter"):
        if filename is not None:
            body["filename"] = filename
    return api._put(f"/config/ruledb/what/{ogroup}/{type_}/{id_}", data=body)


def what_object_delete(api: PmgBackend, ogroup: str, id_: str) -> object:
    """Delete an object from a PMG RuleDB 'what' object group.

    DELETE /config/ruledb/what/{ogroup}/objects/{id}

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 pmgsh-verified path.
    ogroup: numeric ID string (e.g. '8') from what_groups_list response.
    id_: object ID (numeric string) from what_group_objects response.
    Object DELETE always goes through /objects/{id} regardless of type.
    """
    ogroup = _check_ruledb_id(ogroup)
    id_ = _check_ruledb_id(id_)
    return api._delete(f"/config/ruledb/what/{ogroup}/objects/{id_}")


# ---------------------------------------------------------------------------
# W5c MUTATION operations — WHEN-object CRUD
# ---------------------------------------------------------------------------


def when_object_add(
    api: PmgBackend,
    ogroup: str,
    *,
    start: str,
    end: str,
) -> object:
    """Add a timeframe object to a PMG RuleDB 'when' object group.

    POST /config/ruledb/when/{ogroup}/timeframe

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 pmgsh-verified path.
    ogroup: numeric ID string (e.g. '4') from when_groups_list response.
    start: time in H:i format (e.g. '08:00').
    end: time in H:i format (e.g. '17:00').
    """
    ogroup = _check_ruledb_id(ogroup)
    body: dict = {"start": start, "end": end}
    return api._post(f"/config/ruledb/when/{ogroup}/timeframe", data=body)


def when_object_update(
    api: PmgBackend,
    ogroup: str,
    id_: str,
    *,
    start: str,
    end: str,
) -> object:
    """Update a timeframe object in a PMG RuleDB 'when' object group.

    PUT /config/ruledb/when/{ogroup}/timeframe/{id}

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 pmgsh-verified path.
    ogroup: numeric ID string (e.g. '4') from when_groups_list response.
    id_: object ID (numeric string) from when_group_objects response.
    Both start and end are required — PMG 9.1 timeframe PUT enforces both
    even for a single-field change; a partial body returns 400.
    """
    ogroup = _check_ruledb_id(ogroup)
    id_ = _check_ruledb_id(id_)
    body: dict = {"start": start, "end": end}
    return api._put(f"/config/ruledb/when/{ogroup}/timeframe/{id_}", data=body)


def when_object_delete(api: PmgBackend, ogroup: str, id_: str) -> object:
    """Delete an object from a PMG RuleDB 'when' object group.

    DELETE /config/ruledb/when/{ogroup}/objects/{id}

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 pmgsh-verified path.
    ogroup: numeric ID string (e.g. '4') from when_groups_list response.
    id_: object ID (numeric string) from when_group_objects response.
    Object DELETE always goes through /objects/{id} regardless of type.
    """
    ogroup = _check_ruledb_id(ogroup)
    id_ = _check_ruledb_id(id_)
    return api._delete(f"/config/ruledb/when/{ogroup}/objects/{id_}")


# ---------------------------------------------------------------------------
# W5c MUTATION operations — ACTION CRUD
# ---------------------------------------------------------------------------


def action_bcc_create(
    api: PmgBackend,
    *,
    name: str,
    target: str,
    info: str | None = None,
    original: bool | None = None,
) -> object:
    """Create a BCC action object in the PMG RuleDB.

    POST /config/ruledb/action/bcc

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 pmgsh-verified path.
    name: action object name.
    target: target email address for BCC.
    info: optional description.
    original: if True, BCC the original sender (not the recipient).
    """
    body: dict = {"name": name, "target": target}
    if info is not None:
        body["info"] = info
    if original is not None:
        body["original"] = original
    return api._post("/config/ruledb/action/bcc", data=body)


def action_bcc_update(
    api: PmgBackend,
    id_: str,
    *,
    name: str | None = None,
    target: str | None = None,
    info: str | None = None,
    original: bool | None = None,
) -> object:
    """Update a BCC action object in the PMG RuleDB.

    PUT /config/ruledb/action/bcc/{id}

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 pmgsh-verified path.
    id_: compound action object ID (e.g. '13_26') from action_objects_list.
    Only non-None fields are sent; omitted fields keep their current values.
    """
    id_ = _check_action_object_id(id_)
    body: dict = {}
    if name is not None:
        body["name"] = name
    if target is not None:
        body["target"] = target
    if info is not None:
        body["info"] = info
    if original is not None:
        body["original"] = original
    return api._put(f"/config/ruledb/action/bcc/{id_}", data=body)


def action_field_create(
    api: PmgBackend,
    *,
    name: str,
    field: str,
    value: str,
    info: str | None = None,
) -> object:
    """Create a field-modification action object in the PMG RuleDB.

    POST /config/ruledb/action/field

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 pmgsh-verified path.
    name: action object name.
    field: mail header field to set.
    value: value to assign to the header field.
    info: optional description.
    """
    body: dict = {"name": name, "field": field, "value": value}
    if info is not None:
        body["info"] = info
    return api._post("/config/ruledb/action/field", data=body)


def action_field_update(
    api: PmgBackend,
    id_: str,
    *,
    name: str,
    field: str,
    value: str,
    info: str | None = None,
) -> object:
    """Update a field-modification action object in the PMG RuleDB.

    PUT /config/ruledb/action/field/{id}

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 pmgsh-verified path.
    id_: compound action object ID (e.g. '13_26') from action_objects_list.
    name, field, value are all required — PMG 9.1 field action PUT requires
    all three even for a single-field change; a partial body returns 400.
    info: optional description.
    """
    id_ = _check_action_object_id(id_)
    body: dict = {"name": name, "field": field, "value": value}
    if info is not None:
        body["info"] = info
    return api._put(f"/config/ruledb/action/field/{id_}", data=body)


def action_notification_create(
    api: PmgBackend,
    *,
    name: str,
    to: str,
    subject: str,
    body_text: str,
    info: str | None = None,
    attach: bool | None = None,
) -> object:
    """Create a notification action object in the PMG RuleDB.

    POST /config/ruledb/action/notification

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 pmgsh-verified path.
    name: action object name.
    to: recipient email address for the notification.
    subject: notification email subject.
    body_text: notification email body (maps to API param 'body').
    info: optional description.
    attach: if True, attach the original message to the notification.
    """
    body: dict = {"name": name, "to": to, "subject": subject, "body": body_text}
    if info is not None:
        body["info"] = info
    if attach is not None:
        body["attach"] = attach
    return api._post("/config/ruledb/action/notification", data=body)


def action_notification_update(
    api: PmgBackend,
    id_: str,
    *,
    name: str,
    to: str,
    subject: str,
    body_text: str,
    info: str | None = None,
    attach: bool | None = None,
) -> object:
    """Update a notification action object in the PMG RuleDB.

    PUT /config/ruledb/action/notification/{id}

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 pmgsh-verified path.
    id_: compound action object ID (e.g. '13_26') from action_objects_list.
    name, to, subject, body_text are all required — PMG 9.1 notification
    action PUT requires all four even for a single-field change; a partial
    body returns 400.  body_text maps to API param 'body'.
    info: optional description. attach: attach original message.
    """
    id_ = _check_action_object_id(id_)
    body: dict = {"name": name, "to": to, "subject": subject, "body": body_text}
    if info is not None:
        body["info"] = info
    if attach is not None:
        body["attach"] = attach
    return api._put(f"/config/ruledb/action/notification/{id_}", data=body)


def action_disclaimer_create(
    api: PmgBackend,
    *,
    name: str,
    disclaimer: str,
    info: str | None = None,
    position: str | None = None,
    add_separator: bool | None = None,
) -> object:
    """Create a disclaimer action object in the PMG RuleDB.

    POST /config/ruledb/action/disclaimer

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 pmgsh-verified path.
    name: action object name.
    disclaimer: disclaimer text to append/prepend.
    info: optional description.
    position: start|end — where to insert the disclaimer (default: end).
    add_separator: if True, add a separator line (maps to API param 'add-separator').
    """
    if position is not None:
        position = _check_action_position(position)
    body: dict = {"name": name, "disclaimer": disclaimer}
    if info is not None:
        body["info"] = info
    if position is not None:
        body["position"] = position
    if add_separator is not None:
        body["add-separator"] = add_separator
    return api._post("/config/ruledb/action/disclaimer", data=body)


def action_disclaimer_update(
    api: PmgBackend,
    id_: str,
    *,
    name: str | None = None,
    disclaimer: str | None = None,
    info: str | None = None,
    position: str | None = None,
    add_separator: bool | None = None,
) -> object:
    """Update a disclaimer action object in the PMG RuleDB.

    PUT /config/ruledb/action/disclaimer/{id}

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 pmgsh-verified path.
    id_: compound action object ID (e.g. '13_26') from action_objects_list.
    position: start|end (validated if provided).
    add_separator: maps to API param 'add-separator'.
    Only non-None fields are sent; omitted fields keep their current values.
    """
    id_ = _check_action_object_id(id_)
    if position is not None:
        position = _check_action_position(position)
    body: dict = {}
    if name is not None:
        body["name"] = name
    if disclaimer is not None:
        body["disclaimer"] = disclaimer
    if info is not None:
        body["info"] = info
    if position is not None:
        body["position"] = position
    if add_separator is not None:
        body["add-separator"] = add_separator
    return api._put(f"/config/ruledb/action/disclaimer/{id_}", data=body)


def action_removeattachments_create(
    api: PmgBackend,
    *,
    name: str,
    text: str,
    info: str | None = None,
    all_: bool | None = None,
    quarantine: bool | None = None,
) -> object:
    """Create a remove-attachments action object in the PMG RuleDB.

    POST /config/ruledb/action/removeattachments

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 pmgsh-verified path.
    name: action object name.
    text: replacement text for removed attachments.
    info: optional description.
    all_: Python alias for API param 'all' (bool; if True, remove all attachments).
    quarantine: if True, quarantine removed attachments.
    """
    body: dict = {"name": name, "text": text}
    if info is not None:
        body["info"] = info
    if all_ is not None:
        body["all"] = all_
    if quarantine is not None:
        body["quarantine"] = quarantine
    return api._post("/config/ruledb/action/removeattachments", data=body)


def action_removeattachments_update(
    api: PmgBackend,
    id_: str,
    *,
    name: str | None = None,
    text: str | None = None,
    info: str | None = None,
    all_: bool | None = None,
    quarantine: bool | None = None,
) -> object:
    """Update a remove-attachments action object in the PMG RuleDB.

    PUT /config/ruledb/action/removeattachments/{id}

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 pmgsh-verified path.
    id_: compound action object ID (e.g. '13_26') from action_objects_list.
    all_: Python alias for API param 'all' (bool).
    Only non-None fields are sent; omitted fields keep their current values.
    """
    id_ = _check_action_object_id(id_)
    body: dict = {}
    if name is not None:
        body["name"] = name
    if text is not None:
        body["text"] = text
    if info is not None:
        body["info"] = info
    if all_ is not None:
        body["all"] = all_
    if quarantine is not None:
        body["quarantine"] = quarantine
    return api._put(f"/config/ruledb/action/removeattachments/{id_}", data=body)


def action_delete(api: PmgBackend, id_: str) -> object:
    """Delete an action object from the PMG RuleDB.

    DELETE /config/ruledb/action/objects/{id}

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 pmgsh-verified path.
    id_: compound action object ID (e.g. '13_26') from action_objects_list.
    NOTE: PMG rejects deletion of non-editable (built-in) system action objects.
    If the API returns an error for a non-editable action, that error is surfaced cleanly.
    Only action objects with 'editable: true' in action_objects_list can be deleted.
    """
    id_ = _check_action_object_id(id_)
    return api._delete(f"/config/ruledb/action/objects/{id_}")


# ---------------------------------------------------------------------------
# W5c PLAN functions — WHAT/WHEN/ACTION CRUD (PURE — no API call)
# ---------------------------------------------------------------------------


def plan_what_object_add(
    ogroup: str,
    type_: str,
    *,
    contenttype: str | None = None,
    only_content: bool | None = None,
    field: str | None = None,
    value: str | None = None,
    top_part_only: bool | None = None,
    spamlevel: int | None = None,
    filename: str | None = None,
) -> Plan:
    """Preview adding an object to a PMG RuleDB 'what' object group.  PURE — no API call.

    RISK_LOW: additive — adds one object to the group. NOTE: if the group is
    already bound to a rule, the new object affects mail matching immediately.
    """
    ogroup = _check_ruledb_id(ogroup)
    type_ = _check_what_object_type(type_)
    return Plan(
        action="pmg_what_object_add",
        target=f"config/ruledb/what/{ogroup}/{type_}",
        change=f"add {type_} object to 'what' group {ogroup}",
        current={},
        blast_radius=[
            f"adds one {type_} object to 'what' group {ogroup}",
            "additive: no existing objects are removed or modified",
            f"WARNING: if group {ogroup} is already bound to a rule, the new object "
            "affects mail matching immediately on add",
        ],
        risk=RISK_LOW,
        risk_reasons=[
            "additive: adds one object; no existing config or mail deleted",
            "LOW overall — but immediate effect if group is in an active rule",
        ],
        note=f"PMG 9.1 pmgsh-verified path: POST /config/ruledb/what/{{ogroup}}/{type_}.",
    )


def plan_what_object_update(
    ogroup: str,
    type_: str,
    id_: str,
    *,
    contenttype: str | None = None,
    only_content: bool | None = None,
    field: str | None = None,
    value: str | None = None,
    top_part_only: bool | None = None,
    spamlevel: int | None = None,
    filename: str | None = None,
) -> Plan:
    """Preview updating an object in a PMG RuleDB 'what' object group.  PURE — no API call.

    RISK_MEDIUM: modifies an existing object; if the group is bound to an active
    rule, the change affects mail matching immediately.
    """
    ogroup = _check_ruledb_id(ogroup)
    type_ = _check_what_object_type(type_)
    id_ = _check_ruledb_id(id_)
    return Plan(
        action="pmg_what_object_update",
        target=f"config/ruledb/what/{ogroup}/{type_}/{id_}",
        change=f"update {type_} object {id_} in 'what' group {ogroup}",
        current={},
        blast_radius=[
            f"modifies {type_} object {id_} in 'what' group {ogroup}",
            "if the group is bound to an active rule, the change takes effect immediately",
            "verify the new value matches your intended mail content filter target",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=[
            "MEDIUM: modifies an existing object; active rules referencing the group are affected",
            "incorrect value could allow or block unintended mail content immediately",
        ],
        note=f"PMG 9.1 pmgsh-verified path: PUT /config/ruledb/what/{{ogroup}}/{type_}/{{id}}.",
    )


def plan_what_object_delete(ogroup: str, id_: str) -> Plan:
    """Preview deleting an object from a PMG RuleDB 'what' object group.  PURE — no API call.

    RISK_MEDIUM: removes an existing object; if the group is bound to an active
    rule, the change affects mail matching immediately.
    """
    ogroup = _check_ruledb_id(ogroup)
    id_ = _check_ruledb_id(id_)
    return Plan(
        action="pmg_what_object_delete",
        target=f"config/ruledb/what/{ogroup}/objects/{id_}",
        change=f"delete object {id_} from 'what' group {ogroup}",
        current={},
        blast_radius=[
            f"permanently removes object {id_} from 'what' group {ogroup}",
            "if the group is bound to an active rule, the deletion takes effect immediately",
            "content types/patterns previously matched by this object will no longer match",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=[
            "MEDIUM: removes an existing object; cannot be undone without re-adding",
            "active rules referencing the group immediately lose this content match entry",
        ],
        note="PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/what/{ogroup}/objects/{id}.",
    )


def plan_when_object_add(ogroup: str, *, start: str, end: str) -> Plan:
    """Preview adding a timeframe object to a PMG RuleDB 'when' object group.  PURE — no API call.

    RISK_LOW: additive — adds one timeframe object to the group. NOTE: if the group is
    already bound to a rule, the new timeframe affects rule scheduling immediately.
    """
    ogroup = _check_ruledb_id(ogroup)
    return Plan(
        action="pmg_when_object_add",
        target=f"config/ruledb/when/{ogroup}/timeframe",
        change=f"add timeframe {start}-{end} to 'when' group {ogroup}",
        current={},
        blast_radius=[
            f"adds timeframe {start}–{end} to 'when' group {ogroup}",
            "additive: no existing timeframes are removed or modified",
            f"WARNING: if group {ogroup} is already bound to a rule, the new timeframe "
            "affects rule scheduling immediately on add",
        ],
        risk=RISK_LOW,
        risk_reasons=[
            "additive: adds one timeframe; no existing config or mail deleted",
            "LOW overall — but immediate effect if group is in an active rule",
        ],
        note="PMG 9.1 pmgsh-verified path: POST /config/ruledb/when/{ogroup}/timeframe.",
    )


def plan_when_object_update(
    ogroup: str,
    id_: str,
    *,
    start: str | None = None,
    end: str | None = None,
) -> Plan:
    """Preview updating a timeframe object in a PMG RuleDB 'when' object group.  PURE — no API call.

    RISK_MEDIUM: modifies an existing timeframe; if the group is bound to an active
    rule, the change affects rule scheduling immediately.
    """
    ogroup = _check_ruledb_id(ogroup)
    id_ = _check_ruledb_id(id_)
    return Plan(
        action="pmg_when_object_update",
        target=f"config/ruledb/when/{ogroup}/timeframe/{id_}",
        change=f"update timeframe object {id_} in 'when' group {ogroup}",
        current={},
        blast_radius=[
            f"modifies timeframe object {id_} in 'when' group {ogroup}",
            "if the group is bound to an active rule, the change takes effect immediately",
            "verify the new start/end times match your intended scheduling window",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=[
            "MEDIUM: modifies an existing timeframe; active rules referencing the group are affected",
            "incorrect time window could enable or disable rule matching at unintended hours",
        ],
        note="PMG 9.1 pmgsh-verified path: PUT /config/ruledb/when/{ogroup}/timeframe/{id}.",
    )


def plan_when_object_delete(ogroup: str, id_: str) -> Plan:
    """Preview deleting a timeframe object from a PMG RuleDB 'when' object group.  PURE — no API call.

    RISK_MEDIUM: removes an existing timeframe; if the group is bound to an active
    rule, the change affects rule scheduling immediately.
    """
    ogroup = _check_ruledb_id(ogroup)
    id_ = _check_ruledb_id(id_)
    return Plan(
        action="pmg_when_object_delete",
        target=f"config/ruledb/when/{ogroup}/objects/{id_}",
        change=f"delete timeframe object {id_} from 'when' group {ogroup}",
        current={},
        blast_radius=[
            f"permanently removes timeframe object {id_} from 'when' group {ogroup}",
            "if the group is bound to an active rule, the deletion takes effect immediately",
            "the time window removed will no longer constrain rule scheduling",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=[
            "MEDIUM: removes an existing timeframe; cannot be undone without re-adding",
            "active rules referencing the group may now fire at all times if no timeframes remain",
        ],
        note="PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/when/{ogroup}/objects/{id}.",
    )


def plan_action_bcc_create(name: str, target: str) -> Plan:
    """Preview creating a BCC action object in the PMG RuleDB.  PURE — no API call.

    RISK_LOW: additive — creates a new BCC action object; does not affect existing rules
    until the action is attached to a rule (W5d).
    """
    return Plan(
        action="pmg_action_bcc_create",
        target="config/ruledb/action/bcc",
        change=f"create BCC action '{name}' targeting '{target}'",
        current={},
        blast_radius=[
            f"creates a new BCC action object named '{name}' with target '{target}'",
            "additive: does not affect existing action objects or mail flow",
            "the action has no effect until attached to a rule (W5d)",
        ],
        risk=RISK_LOW,
        risk_reasons=[
            "additive: creates one action object; no existing config or mail deleted",
            "LOW: action is inactive until bound to a rule",
        ],
        note="PMG 9.1 pmgsh-verified path: POST /config/ruledb/action/bcc.",
    )


def plan_action_bcc_update(id_: str) -> Plan:
    """Preview updating a BCC action object in the PMG RuleDB.  PURE — no API call.

    RISK_MEDIUM: modifies an existing action; active rules referencing it are affected.
    """
    id_ = _check_action_object_id(id_)
    return Plan(
        action="pmg_action_bcc_update",
        target=f"config/ruledb/action/bcc/{id_}",
        change=f"update BCC action object {id_}",
        current={},
        blast_radius=[
            f"modifies BCC action object {id_}",
            "if the action is attached to an active rule, the change takes effect immediately",
            "BCC target change affects where copies of matched mail are sent",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=[
            "MEDIUM: modifies an existing action; active rules referencing it are affected",
            "incorrect target could BCC mail to unintended recipients",
        ],
        note="PMG 9.1 pmgsh-verified path: PUT /config/ruledb/action/bcc/{id}.",
    )


def plan_action_field_create(name: str, field: str, value: str) -> Plan:
    """Preview creating a field-modification action object in the PMG RuleDB.  PURE — no API call.

    RISK_LOW: additive — creates a new field action object; inactive until attached to a rule.
    """
    return Plan(
        action="pmg_action_field_create",
        target="config/ruledb/action/field",
        change=f"create field action '{name}': set {field}={value!r}",
        current={},
        blast_radius=[
            f"creates a new field action named '{name}' that sets header '{field}' to '{value}'",
            "additive: does not affect existing action objects or mail flow",
            "the action has no effect until attached to a rule (W5d)",
        ],
        risk=RISK_LOW,
        risk_reasons=[
            "additive: creates one action object; no existing config or mail deleted",
            "LOW: action is inactive until bound to a rule",
        ],
        note="PMG 9.1 pmgsh-verified path: POST /config/ruledb/action/field.",
    )


def plan_action_field_update(id_: str) -> Plan:
    """Preview updating a field-modification action object in the PMG RuleDB.  PURE — no API call.

    RISK_MEDIUM: modifies an existing action; active rules referencing it are affected.
    """
    id_ = _check_action_object_id(id_)
    return Plan(
        action="pmg_action_field_update",
        target=f"config/ruledb/action/field/{id_}",
        change=f"update field action object {id_}",
        current={},
        blast_radius=[
            f"modifies field action object {id_}",
            "if the action is attached to an active rule, the change takes effect immediately",
            "field change affects what header value is injected into matched messages",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=[
            "MEDIUM: modifies an existing action; active rules referencing it are affected",
            "incorrect field/value could inject wrong headers into matched messages",
        ],
        note="PMG 9.1 pmgsh-verified path: PUT /config/ruledb/action/field/{id}.",
    )


def plan_action_notification_create(name: str, to: str) -> Plan:
    """Preview creating a notification action object in the PMG RuleDB.  PURE — no API call.

    RISK_LOW: additive — creates a new notification action object; inactive until attached.
    """
    return Plan(
        action="pmg_action_notification_create",
        target="config/ruledb/action/notification",
        change=f"create notification action '{name}' sending to '{to}'",
        current={},
        blast_radius=[
            f"creates a new notification action named '{name}' that sends to '{to}'",
            "additive: does not affect existing action objects or mail flow",
            "the action has no effect until attached to a rule (W5d)",
        ],
        risk=RISK_LOW,
        risk_reasons=[
            "additive: creates one action object; no existing config or mail deleted",
            "LOW: action is inactive until bound to a rule",
        ],
        note="PMG 9.1 pmgsh-verified path: POST /config/ruledb/action/notification.",
    )


def plan_action_notification_update(id_: str) -> Plan:
    """Preview updating a notification action object in the PMG RuleDB.  PURE — no API call.

    RISK_MEDIUM: modifies an existing action; active rules referencing it are affected.
    """
    id_ = _check_action_object_id(id_)
    return Plan(
        action="pmg_action_notification_update",
        target=f"config/ruledb/action/notification/{id_}",
        change=f"update notification action object {id_}",
        current={},
        blast_radius=[
            f"modifies notification action object {id_}",
            "if the action is attached to an active rule, the change takes effect immediately",
            "recipient/subject/body changes affect notifications sent for matched mail",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=[
            "MEDIUM: modifies an existing action; active rules referencing it are affected",
            "incorrect recipient could send notifications to unintended addresses",
        ],
        note="PMG 9.1 pmgsh-verified path: PUT /config/ruledb/action/notification/{id}.",
    )


def plan_action_disclaimer_create(name: str) -> Plan:
    """Preview creating a disclaimer action object in the PMG RuleDB.  PURE — no API call.

    RISK_LOW: additive — creates a new disclaimer action object; inactive until attached.
    """
    return Plan(
        action="pmg_action_disclaimer_create",
        target="config/ruledb/action/disclaimer",
        change=f"create disclaimer action '{name}'",
        current={},
        blast_radius=[
            f"creates a new disclaimer action named '{name}'",
            "additive: does not affect existing action objects or mail flow",
            "the action has no effect until attached to a rule (W5d)",
        ],
        risk=RISK_LOW,
        risk_reasons=[
            "additive: creates one action object; no existing config or mail deleted",
            "LOW: action is inactive until bound to a rule",
        ],
        note="PMG 9.1 pmgsh-verified path: POST /config/ruledb/action/disclaimer.",
    )


def plan_action_disclaimer_update(id_: str) -> Plan:
    """Preview updating a disclaimer action object in the PMG RuleDB.  PURE — no API call.

    RISK_MEDIUM: modifies an existing action; active rules referencing it are affected.
    """
    id_ = _check_action_object_id(id_)
    return Plan(
        action="pmg_action_disclaimer_update",
        target=f"config/ruledb/action/disclaimer/{id_}",
        change=f"update disclaimer action object {id_}",
        current={},
        blast_radius=[
            f"modifies disclaimer action object {id_}",
            "if the action is attached to an active rule, the change takes effect immediately",
            "disclaimer text/position changes affect all messages matched by rules using this action",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=[
            "MEDIUM: modifies an existing action; active rules referencing it are affected",
            "disclaimer change affects all mail processed by rules using this action",
        ],
        note="PMG 9.1 pmgsh-verified path: PUT /config/ruledb/action/disclaimer/{id}.",
    )


def plan_action_removeattachments_create(name: str) -> Plan:
    """Preview creating a remove-attachments action object in the PMG RuleDB.  PURE — no API call.

    RISK_LOW: additive — creates a new remove-attachments action object; inactive until attached.
    """
    return Plan(
        action="pmg_action_removeattachments_create",
        target="config/ruledb/action/removeattachments",
        change=f"create remove-attachments action '{name}'",
        current={},
        blast_radius=[
            f"creates a new remove-attachments action named '{name}'",
            "additive: does not affect existing action objects or mail flow",
            "the action has no effect until attached to a rule (W5d)",
        ],
        risk=RISK_LOW,
        risk_reasons=[
            "additive: creates one action object; no existing config or mail deleted",
            "LOW: action is inactive until bound to a rule",
        ],
        note="PMG 9.1 pmgsh-verified path: POST /config/ruledb/action/removeattachments.",
    )


def plan_action_removeattachments_update(id_: str) -> Plan:
    """Preview updating a remove-attachments action object in the PMG RuleDB.  PURE — no API call.

    RISK_MEDIUM: modifies an existing action; active rules referencing it are affected.
    """
    id_ = _check_action_object_id(id_)
    return Plan(
        action="pmg_action_removeattachments_update",
        target=f"config/ruledb/action/removeattachments/{id_}",
        change=f"update remove-attachments action object {id_}",
        current={},
        blast_radius=[
            f"modifies remove-attachments action object {id_}",
            "if the action is attached to an active rule, the change takes effect immediately",
            "changes to all/quarantine/text affect how attachments are removed from matched mail",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=[
            "MEDIUM: modifies an existing action; active rules referencing it are affected",
            "quarantine behavior change affects where stripped attachments are stored",
        ],
        note="PMG 9.1 pmgsh-verified path: PUT /config/ruledb/action/removeattachments/{id}.",
    )


def plan_action_delete(id_: str) -> Plan:
    """Preview deleting an action object from the PMG RuleDB.  PURE — no API call.

    RISK_MEDIUM: deletes an action object; rules referencing it will lose the action.
    NOTE: PMG rejects deletion of non-editable (built-in) system action objects.
    """
    id_ = _check_action_object_id(id_)
    return Plan(
        action="pmg_action_delete",
        target=f"config/ruledb/action/objects/{id_}",
        change=f"delete action object {id_}",
        current={},
        blast_radius=[
            f"permanently removes action object {id_} from the PMG RuleDB",
            "rules that reference this action will lose it upon next evaluation",
            "WARNING: PMG rejects deletion of non-editable (built-in) system actions",
            "check 'editable' flag in pmg_action_objects_list before confirming",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=[
            "MEDIUM: deletes an action object; cannot be undone without re-creating",
            "rules referencing this action may stop applying the intended action",
        ],
        note="PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/action/objects/{id}.",
    )


# ---------------------------------------------------------------------------
# W5d Validators
# ---------------------------------------------------------------------------


def _check_direction(direction: int) -> int:
    """Validate a PMG rule direction value: 0 (in), 1 (out), or 2 (both)."""
    try:
        d = int(direction)
    except (ValueError, TypeError) as exc:
        raise ProximoError(
            f"invalid direction: {direction!r} — must be 0 (in), 1 (out), or 2 (both)"
        ) from exc
    if d not in (0, 1, 2):
        raise ProximoError(
            f"invalid direction: {direction!r} — must be 0 (in), 1 (out), or 2 (both)"
        )
    return d


def _check_priority(priority: int) -> int:
    """Validate a PMG rule priority value: integer in range 0-100."""
    try:
        p = int(priority)
    except (ValueError, TypeError) as exc:
        raise ProximoError(
            f"invalid priority: {priority!r} — must be an integer in range 0-100"
        ) from exc
    if not (0 <= p <= 100):
        raise ProximoError(
            f"invalid priority: {priority!r} — must be in range 0-100"
        )
    return p


# ---------------------------------------------------------------------------
# W5d MUTATION operations — rule CRUD + rule↔group attach/detach
# ---------------------------------------------------------------------------


def ruledb_rule_create(
    api: PmgBackend,
    name: str,
    priority: int,
    active: bool = False,
    direction: int | None = None,
    from_and: bool | None = None,
    from_invert: bool | None = None,
    to_and: bool | None = None,
    to_invert: bool | None = None,
    what_and: bool | None = None,
    what_invert: bool | None = None,
    when_and: bool | None = None,
    when_invert: bool | None = None,
) -> object:
    """Create a PMG RuleDB rule.

    POST /config/ruledb/rules

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 pmgsh-verified path.
    name: rule name.
    priority: 0-100 (lower = higher priority in PMG processing order).
    active: whether the rule is active — DEFAULTS TO FALSE (safety default).
            Rules control live mail processing; confirm active=True only when
            the rule configuration has been verified.
    direction: 0=inbound, 1=outbound, 2=both.
    from_and/from_invert/to_and/to_invert/what_and/what_invert/when_and/when_invert:
        bool flags controlling AND/invert logic for each slot — maps to the
        hyphen-param API names (from-and, from-invert, etc.).
    Returns the numeric rule ID assigned by PMG.
    """
    priority_int = _check_priority(priority)
    body: dict = {"name": name, "priority": priority_int, "active": active}
    if direction is not None:
        body["direction"] = _check_direction(direction)
    if from_and is not None:
        body["from-and"] = from_and
    if from_invert is not None:
        body["from-invert"] = from_invert
    if to_and is not None:
        body["to-and"] = to_and
    if to_invert is not None:
        body["to-invert"] = to_invert
    if what_and is not None:
        body["what-and"] = what_and
    if what_invert is not None:
        body["what-invert"] = what_invert
    if when_and is not None:
        body["when-and"] = when_and
    if when_invert is not None:
        body["when-invert"] = when_invert
    return api._post("/config/ruledb/rules", data=body)


def ruledb_rule_update(
    api: PmgBackend,
    id_: str,
    name: str | None = None,
    priority: int | None = None,
    active: bool | None = None,
    direction: int | None = None,
    from_and: bool | None = None,
    from_invert: bool | None = None,
    to_and: bool | None = None,
    to_invert: bool | None = None,
    what_and: bool | None = None,
    what_invert: bool | None = None,
    when_and: bool | None = None,
    when_invert: bool | None = None,
) -> object:
    """Update a PMG RuleDB rule's configuration.

    PUT /config/ruledb/rules/{id}/config

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 pmgsh-verified path.
    id_: rule ID (positive integer string, e.g. '100').
    All fields are optional; only non-None values are sent.
    WARNING: setting active=True activates the rule and begins live mail processing.
    """
    id_ = _check_ruledb_id(id_)
    body: dict = {}
    if name is not None:
        body["name"] = name
    if priority is not None:
        body["priority"] = _check_priority(priority)
    if active is not None:
        body["active"] = active
    if direction is not None:
        body["direction"] = _check_direction(direction)
    if from_and is not None:
        body["from-and"] = from_and
    if from_invert is not None:
        body["from-invert"] = from_invert
    if to_and is not None:
        body["to-and"] = to_and
    if to_invert is not None:
        body["to-invert"] = to_invert
    if what_and is not None:
        body["what-and"] = what_and
    if what_invert is not None:
        body["what-invert"] = what_invert
    if when_and is not None:
        body["when-and"] = when_and
    if when_invert is not None:
        body["when-invert"] = when_invert
    return api._put(f"/config/ruledb/rules/{id_}/config", data=body)


def ruledb_rule_delete(api: PmgBackend, id_: str) -> object:
    """Delete a PMG RuleDB rule.

    DELETE /config/ruledb/rules/{id}

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 pmgsh-verified path.
    id_: rule ID (positive integer string, e.g. '100').
    WARNING: permanently removes the rule and detaches all group bindings.
    """
    id_ = _check_ruledb_id(id_)
    return api._delete(f"/config/ruledb/rules/{id_}")


def ruledb_rule_from_attach(api: PmgBackend, id_: str, ogroup: str) -> object:
    """Attach a 'from' (sender/who) object group to a PMG RuleDB rule.

    POST /config/ruledb/rules/{id}/from

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 pmgsh-verified path.
    id_: rule ID (positive integer string, e.g. '100').
    ogroup: numeric ID of the who-group to attach (from pmg_who_groups_list).
    """
    id_ = _check_ruledb_id(id_)
    ogroup = _check_ruledb_id(ogroup)
    return api._post(f"/config/ruledb/rules/{id_}/from", data={"ogroup": ogroup})


def ruledb_rule_from_detach(api: PmgBackend, id_: str, ogroup: str) -> object:
    """Detach a 'from' (sender/who) object group from a PMG RuleDB rule.

    DELETE /config/ruledb/rules/{id}/from/{ogroup}

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 pmgsh-verified path.
    id_: rule ID (positive integer string, e.g. '100').
    ogroup: numeric ID of the who-group to detach.
    """
    id_ = _check_ruledb_id(id_)
    ogroup = _check_ruledb_id(ogroup)
    return api._delete(f"/config/ruledb/rules/{id_}/from/{ogroup}")


def ruledb_rule_to_attach(api: PmgBackend, id_: str, ogroup: str) -> object:
    """Attach a 'to' (recipient/who) object group to a PMG RuleDB rule.

    POST /config/ruledb/rules/{id}/to

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 pmgsh-verified path.
    id_: rule ID (positive integer string, e.g. '100').
    ogroup: numeric ID of the who-group to attach (from pmg_who_groups_list).
    """
    id_ = _check_ruledb_id(id_)
    ogroup = _check_ruledb_id(ogroup)
    return api._post(f"/config/ruledb/rules/{id_}/to", data={"ogroup": ogroup})


def ruledb_rule_to_detach(api: PmgBackend, id_: str, ogroup: str) -> object:
    """Detach a 'to' (recipient/who) object group from a PMG RuleDB rule.

    DELETE /config/ruledb/rules/{id}/to/{ogroup}

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 pmgsh-verified path.
    id_: rule ID (positive integer string, e.g. '100').
    ogroup: numeric ID of the who-group to detach.
    """
    id_ = _check_ruledb_id(id_)
    ogroup = _check_ruledb_id(ogroup)
    return api._delete(f"/config/ruledb/rules/{id_}/to/{ogroup}")


def ruledb_rule_what_attach(api: PmgBackend, id_: str, ogroup: str) -> object:
    """Attach a 'what' (content) object group to a PMG RuleDB rule.

    POST /config/ruledb/rules/{id}/what

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 pmgsh-verified path.
    id_: rule ID (positive integer string, e.g. '100').
    ogroup: numeric ID of the what-group to attach (from pmg_what_groups_list).
    """
    id_ = _check_ruledb_id(id_)
    ogroup = _check_ruledb_id(ogroup)
    return api._post(f"/config/ruledb/rules/{id_}/what", data={"ogroup": ogroup})


def ruledb_rule_what_detach(api: PmgBackend, id_: str, ogroup: str) -> object:
    """Detach a 'what' (content) object group from a PMG RuleDB rule.

    DELETE /config/ruledb/rules/{id}/what/{ogroup}

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 pmgsh-verified path.
    id_: rule ID (positive integer string, e.g. '100').
    ogroup: numeric ID of the what-group to detach.
    """
    id_ = _check_ruledb_id(id_)
    ogroup = _check_ruledb_id(ogroup)
    return api._delete(f"/config/ruledb/rules/{id_}/what/{ogroup}")


def ruledb_rule_when_attach(api: PmgBackend, id_: str, ogroup: str) -> object:
    """Attach a 'when' (timeframe) object group to a PMG RuleDB rule.

    POST /config/ruledb/rules/{id}/when

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 pmgsh-verified path.
    id_: rule ID (positive integer string, e.g. '100').
    ogroup: numeric ID of the when-group to attach (from pmg_when_groups_list).
    """
    id_ = _check_ruledb_id(id_)
    ogroup = _check_ruledb_id(ogroup)
    return api._post(f"/config/ruledb/rules/{id_}/when", data={"ogroup": ogroup})


def ruledb_rule_when_detach(api: PmgBackend, id_: str, ogroup: str) -> object:
    """Detach a 'when' (timeframe) object group from a PMG RuleDB rule.

    DELETE /config/ruledb/rules/{id}/when/{ogroup}

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 pmgsh-verified path.
    id_: rule ID (positive integer string, e.g. '100').
    ogroup: numeric ID of the when-group to detach.
    """
    id_ = _check_ruledb_id(id_)
    ogroup = _check_ruledb_id(ogroup)
    return api._delete(f"/config/ruledb/rules/{id_}/when/{ogroup}")


def ruledb_rule_action_attach(api: PmgBackend, id_: str, ogroup: str) -> object:
    """Attach an action object group to a PMG RuleDB rule.

    POST /config/ruledb/rules/{id}/action

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 live-verified path: singular /action (not /actions — that path returns 501).
    id_: rule ID (positive integer string, e.g. '100').
    ogroup: numeric group-ID of the action group to attach (the integer part before '_' in
        a compound action id like '13_26'; from pmg_action_objects_list).
    """
    id_ = _check_ruledb_id(id_)
    ogroup = _check_ruledb_id(ogroup)
    return api._post(f"/config/ruledb/rules/{id_}/action", data={"ogroup": ogroup})


def ruledb_rule_action_detach(api: PmgBackend, id_: str, ogroup: str) -> object:
    """Detach an action object group from a PMG RuleDB rule.

    DELETE /config/ruledb/rules/{id}/action/{ogroup}

    MUTATION — confirm-gated + audited at the server layer.

    PMG 9.1 live-verified path: singular /action (not /actions — that path returns 501).
    id_: rule ID (positive integer string, e.g. '100').
    ogroup: numeric group-ID of the action group to detach.
    """
    id_ = _check_ruledb_id(id_)
    ogroup = _check_ruledb_id(ogroup)
    return api._delete(f"/config/ruledb/rules/{id_}/action/{ogroup}")


# ---------------------------------------------------------------------------
# W5d PLAN functions — rule CRUD + attach/detach (PURE — no API call)
# ---------------------------------------------------------------------------

_RULE_MAIL_FLOW_WARNING = (
    "Rules control live mail processing. An active rule (active=1) at low priority "
    "with broad who/what groups can affect ALL mail flow."
)


def plan_ruledb_rule_create(
    name: str,
    priority: int,
    active: bool = False,
    direction: int | None = None,
    from_and: bool | None = None,
    from_invert: bool | None = None,
    to_and: bool | None = None,
    to_invert: bool | None = None,
    what_and: bool | None = None,
    what_invert: bool | None = None,
    when_and: bool | None = None,
    when_invert: bool | None = None,
) -> Plan:
    """Preview creating a PMG RuleDB rule.  PURE — no API call.

    RISK_MEDIUM: rules control live mail processing.
    active DEFAULTS TO FALSE — inactive rules do not affect mail flow until activated.
    """
    priority_int = _check_priority(priority)
    if direction is not None:
        _check_direction(direction)
    dir_str = {0: "inbound", 1: "outbound", 2: "both"}.get(
        direction if direction is not None else -1, "not set"
    )
    return Plan(
        action="pmg_ruledb_rule_create",
        target="config/ruledb/rules",
        change=f"create RuleDB rule '{name}' (priority={priority_int}, active={active})",
        current={},
        blast_radius=[
            f"creates rule '{name}' with priority={priority_int}, direction={dir_str}",
            f"active={active} — {'RULE IS INACTIVE: will not affect mail flow until activated'
               if not active else 'RULE IS ACTIVE: will affect live mail processing immediately'}",
            _RULE_MAIL_FLOW_WARNING,
            "attach who/what/when/action groups before activating to ensure correct scope",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=[
            "MEDIUM: rules control live mail processing; even an inactive rule becomes "
            "active if updated with active=True",
            "LOW risk when active=False (default); review all group attachments before activating",
        ],
        note="PMG 9.1 pmgsh-verified path: POST /config/ruledb/rules.",
    )


def plan_ruledb_rule_update(
    id_: str,
    name: str | None = None,
    priority: int | None = None,
    active: bool | None = None,
    direction: int | None = None,
    from_and: bool | None = None,
    from_invert: bool | None = None,
    to_and: bool | None = None,
    to_invert: bool | None = None,
    what_and: bool | None = None,
    what_invert: bool | None = None,
    when_and: bool | None = None,
    when_invert: bool | None = None,
) -> Plan:
    """Preview updating a PMG RuleDB rule's configuration.  PURE — no API call.

    RISK_MEDIUM: modifying a rule can change live mail processing immediately
    if the rule is active.  Setting active=True activates the rule.
    """
    id_ = _check_ruledb_id(id_)
    if priority is not None:
        _check_priority(priority)
    if direction is not None:
        _check_direction(direction)
    active_note = (
        "WARNING: setting active=True activates the rule and begins live mail processing"
        if active is True
        else "active flag is not being changed by this update"
        if active is None
        else "setting active=False deactivates the rule (stops mail processing)"
    )
    return Plan(
        action="pmg_ruledb_rule_update",
        target=f"config/ruledb/rules/{id_}/config",
        change=f"update RuleDB rule {id_} configuration",
        current={},
        blast_radius=[
            f"modifies configuration of rule {id_}",
            active_note,
            _RULE_MAIL_FLOW_WARNING,
            "changes to an active rule take effect immediately on new mail",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=[
            "MEDIUM: rule config changes can alter live mail processing immediately",
            "setting active=True starts processing mail against this rule's groups",
        ],
        note="PMG 9.1 pmgsh-verified path: PUT /config/ruledb/rules/{id}/config.",
    )


def plan_ruledb_rule_delete(id_: str) -> Plan:
    """Preview deleting a PMG RuleDB rule.  PURE — no API call.

    RISK_MEDIUM: permanently removes the rule and all its group bindings.
    """
    id_ = _check_ruledb_id(id_)
    return Plan(
        action="pmg_ruledb_rule_delete",
        target=f"config/ruledb/rules/{id_}",
        change=f"delete RuleDB rule {id_}",
        current={},
        blast_radius=[
            f"permanently removes rule {id_} from the PMG RuleDB",
            "all group attachments (from/to/what/when/action) are also removed",
            "if the rule was active, its mail processing effect stops immediately",
            "the rule cannot be recovered without re-creation and re-attachment of groups",
        ],
        risk=RISK_MEDIUM,
        risk_reasons=[
            "MEDIUM: permanently removes a rule; cannot be undone without full re-creation",
            "if active, the rule's mail filtering effect stops on deletion",
        ],
        note="PMG 9.1 pmgsh-verified path: DELETE /config/ruledb/rules/{id}.",
    )


def _attach_detach_plan(
    action: str,
    target: str,
    change: str,
    id_: str,
    ogroup: str,
    slot: str,
    verb: str,
) -> Plan:
    """Shared plan builder for rule↔group attach/detach operations."""
    return Plan(
        action=action,
        target=target,
        change=change,
        current={},
        blast_radius=[
            f"{verb}s '{slot}' group {ogroup} {'to' if 'attach' in action else 'from'} rule {id_}",
            "modifies which mail a rule matches; only affects flow if the rule is active",
            _RULE_MAIL_FLOW_WARNING,
        ],
        risk=RISK_MEDIUM,
        risk_reasons=[
            f"MEDIUM: {verb}ing a group modifies rule matching scope",
            "only affects live mail if the rule is active; confirm rule state before proceeding",
        ],
        note=f"PMG 9.1 pmgsh-verified path: {target.replace('config/', '/config/', 1)}.",
    )


def plan_ruledb_rule_from_attach(id_: str, ogroup: str) -> Plan:
    """Preview attaching a 'from' (sender/who) group to a PMG RuleDB rule.  PURE — no API call.

    RISK_MEDIUM: modifies which mail a rule matches; only affects flow if the rule is active.
    """
    id_ = _check_ruledb_id(id_)
    ogroup = _check_ruledb_id(ogroup)
    return _attach_detach_plan(
        action="pmg_ruledb_rule_from_attach",
        target=f"config/ruledb/rules/{id_}/from",
        change=f"attach 'from' group {ogroup} to rule {id_}",
        id_=id_, ogroup=ogroup, slot="from", verb="attach",
    )


def plan_ruledb_rule_from_detach(id_: str, ogroup: str) -> Plan:
    """Preview detaching a 'from' (sender/who) group from a PMG RuleDB rule.  PURE — no API call.

    RISK_MEDIUM: modifies which mail a rule matches; only affects flow if the rule is active.
    """
    id_ = _check_ruledb_id(id_)
    ogroup = _check_ruledb_id(ogroup)
    return _attach_detach_plan(
        action="pmg_ruledb_rule_from_detach",
        target=f"config/ruledb/rules/{id_}/from/{ogroup}",
        change=f"detach 'from' group {ogroup} from rule {id_}",
        id_=id_, ogroup=ogroup, slot="from", verb="detach",
    )


def plan_ruledb_rule_to_attach(id_: str, ogroup: str) -> Plan:
    """Preview attaching a 'to' (recipient/who) group to a PMG RuleDB rule.  PURE — no API call.

    RISK_MEDIUM: modifies which mail a rule matches; only affects flow if the rule is active.
    """
    id_ = _check_ruledb_id(id_)
    ogroup = _check_ruledb_id(ogroup)
    return _attach_detach_plan(
        action="pmg_ruledb_rule_to_attach",
        target=f"config/ruledb/rules/{id_}/to",
        change=f"attach 'to' group {ogroup} to rule {id_}",
        id_=id_, ogroup=ogroup, slot="to", verb="attach",
    )


def plan_ruledb_rule_to_detach(id_: str, ogroup: str) -> Plan:
    """Preview detaching a 'to' (recipient/who) group from a PMG RuleDB rule.  PURE — no API call.

    RISK_MEDIUM: modifies which mail a rule matches; only affects flow if the rule is active.
    """
    id_ = _check_ruledb_id(id_)
    ogroup = _check_ruledb_id(ogroup)
    return _attach_detach_plan(
        action="pmg_ruledb_rule_to_detach",
        target=f"config/ruledb/rules/{id_}/to/{ogroup}",
        change=f"detach 'to' group {ogroup} from rule {id_}",
        id_=id_, ogroup=ogroup, slot="to", verb="detach",
    )


def plan_ruledb_rule_what_attach(id_: str, ogroup: str) -> Plan:
    """Preview attaching a 'what' (content) group to a PMG RuleDB rule.  PURE — no API call.

    RISK_MEDIUM: modifies which mail a rule matches; only affects flow if the rule is active.
    """
    id_ = _check_ruledb_id(id_)
    ogroup = _check_ruledb_id(ogroup)
    return _attach_detach_plan(
        action="pmg_ruledb_rule_what_attach",
        target=f"config/ruledb/rules/{id_}/what",
        change=f"attach 'what' group {ogroup} to rule {id_}",
        id_=id_, ogroup=ogroup, slot="what", verb="attach",
    )


def plan_ruledb_rule_what_detach(id_: str, ogroup: str) -> Plan:
    """Preview detaching a 'what' (content) group from a PMG RuleDB rule.  PURE — no API call.

    RISK_MEDIUM: modifies which mail a rule matches; only affects flow if the rule is active.
    """
    id_ = _check_ruledb_id(id_)
    ogroup = _check_ruledb_id(ogroup)
    return _attach_detach_plan(
        action="pmg_ruledb_rule_what_detach",
        target=f"config/ruledb/rules/{id_}/what/{ogroup}",
        change=f"detach 'what' group {ogroup} from rule {id_}",
        id_=id_, ogroup=ogroup, slot="what", verb="detach",
    )


def plan_ruledb_rule_when_attach(id_: str, ogroup: str) -> Plan:
    """Preview attaching a 'when' (timeframe) group to a PMG RuleDB rule.  PURE — no API call.

    RISK_MEDIUM: modifies which mail a rule matches; only affects flow if the rule is active.
    """
    id_ = _check_ruledb_id(id_)
    ogroup = _check_ruledb_id(ogroup)
    return _attach_detach_plan(
        action="pmg_ruledb_rule_when_attach",
        target=f"config/ruledb/rules/{id_}/when",
        change=f"attach 'when' group {ogroup} to rule {id_}",
        id_=id_, ogroup=ogroup, slot="when", verb="attach",
    )


def plan_ruledb_rule_when_detach(id_: str, ogroup: str) -> Plan:
    """Preview detaching a 'when' (timeframe) group from a PMG RuleDB rule.  PURE — no API call.

    RISK_MEDIUM: modifies which mail a rule matches; only affects flow if the rule is active.
    """
    id_ = _check_ruledb_id(id_)
    ogroup = _check_ruledb_id(ogroup)
    return _attach_detach_plan(
        action="pmg_ruledb_rule_when_detach",
        target=f"config/ruledb/rules/{id_}/when/{ogroup}",
        change=f"detach 'when' group {ogroup} from rule {id_}",
        id_=id_, ogroup=ogroup, slot="when", verb="detach",
    )


def plan_ruledb_rule_action_attach(id_: str, ogroup: str) -> Plan:
    """Preview attaching an action group to a PMG RuleDB rule.  PURE — no API call.

    RISK_MEDIUM: modifies which mail a rule matches; only affects flow if the rule is active.
    """
    id_ = _check_ruledb_id(id_)
    ogroup = _check_ruledb_id(ogroup)
    return _attach_detach_plan(
        action="pmg_ruledb_rule_action_attach",
        target=f"config/ruledb/rules/{id_}/action",
        change=f"attach action group {ogroup} to rule {id_}",
        id_=id_, ogroup=ogroup, slot="action", verb="attach",
    )


def plan_ruledb_rule_action_detach(id_: str, ogroup: str) -> Plan:
    """Preview detaching an action group from a PMG RuleDB rule.  PURE — no API call.

    RISK_MEDIUM: modifies which mail a rule matches; only affects flow if the rule is active.
    """
    id_ = _check_ruledb_id(id_)
    ogroup = _check_ruledb_id(ogroup)
    return _attach_detach_plan(
        action="pmg_ruledb_rule_action_detach",
        target=f"config/ruledb/rules/{id_}/action/{ogroup}",
        change=f"detach action group {ogroup} from rule {id_}",
        id_=id_, ogroup=ogroup, slot="action", verb="detach",
    )
