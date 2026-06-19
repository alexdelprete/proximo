"""Build the A2A AgentCard for Proximo.

This module provides a single factory function, ``build_agent_card``, that
assembles the machine-readable capability advertisement for Proximo's A2A face.
It maps the curated skill slice (``SKILLS``) 1-to-1 onto ``AgentSkill`` entries
and exposes a single JSON-RPC 2.0 interface at the caller-supplied URL.

Security note: auth is ENFORCED at the server layer (``app.py``) — a non-localhost bind is refused
without a token, and when a token is set the JSON-RPC control endpoint requires ``Authorization:
Bearer`` (plus Host-header validation as a DNS-rebind guard). When built with ``secured=True`` the
card DECLARES the bearer scheme (``security_schemes`` + a ``security_requirements`` entry) so A2A
clients self-configure from discovery rather than learning auth only from a 401. The card stays
readable so clients can fetch it before authenticating.
"""

from __future__ import annotations

import importlib.metadata

from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    SecurityRequirement,
)
from a2a.utils.constants import PROTOCOL_VERSION_CURRENT, TransportProtocol

from proximo import __version__ as _FALLBACK_VERSION

from .signing import OperatorKey, sign_card
from .skills import SKILLS


def build_agent_card(
    rpc_url: str,
    version: str | None = None,
    *,
    secured: bool = False,
    signing_key: OperatorKey | None = None,
    jwks_url: str | None = None,
) -> AgentCard:
    """Build the Proximo AgentCard for a given JSON-RPC endpoint URL.

    Args:
        rpc_url:  The fully-qualified URL at which the A2A JSON-RPC endpoint is
                  served (e.g. ``http://localhost:8080/``).  This is embedded in
                  the returned card's ``supported_interfaces`` list so that A2A
                  clients know where to send requests.
        version:  Override the package version string.  Only used if
                  ``importlib.metadata`` cannot find the installed package.

    Returns:
        A fully populated ``AgentCard`` protobuf message.
    """
    try:
        pkg_version = importlib.metadata.version("proximo")
    except importlib.metadata.PackageNotFoundError:
        pkg_version = version or _FALLBACK_VERSION

    skills = [
        AgentSkill(
            id=s.id,
            name=s.name,
            description=s.description,
            tags=list(s.tags),
            examples=list(s.examples),
        )
        for s in SKILLS
    ]

    interface = AgentInterface(
        url=rpc_url,
        protocol_binding=TransportProtocol.JSONRPC,
        protocol_version=PROTOCOL_VERSION_CURRENT,
    )

    card = AgentCard(
        name="Proximo",
        description=(
            "The ethical Proxmox operator agent — one trust core, two faces (MCP + A2A). "
            "Every mutation is planned, audited, and reversible by construction."
        ),
        version=pkg_version,
        capabilities=AgentCapabilities(streaming=False, push_notifications=False),
        supported_interfaces=[interface],
        default_input_modes=["application/json", "text/plain"],
        default_output_modes=["application/json", "text/plain"],
        skills=skills,
    )

    if secured:
        # Declare the bearer scheme the server enforces (app.py), so A2A clients can self-configure
        # from discovery instead of learning it only from a 401. Scopeless requirement.
        card.security_schemes["bearerAuth"].http_auth_security_scheme.scheme = "bearer"
        req = SecurityRequirement()
        _ = req.schemes["bearerAuth"]  # auto-creates an empty StringList (no scopes)
        card.security_requirements.append(req)

    if signing_key is not None:
        # SIGNET: press the operator's ES256 seal onto the card (jku → the served JWKS).
        sign_card(card, signing_key, jku=jwks_url)

    return card
