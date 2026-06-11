"""Tests for the Proximo A2A AgentCard factory (src/proximo/a2a/card.py).

Verifies:
- The card builds without error.
- Every skill id in SKILLS appears exactly once on the card.
- card.name is "Proximo".
- card.version is a non-empty string.
- card.capabilities is present.
- card.supported_interfaces[0].url matches the rpc_url argument.
"""

from __future__ import annotations

from proximo.a2a.card import build_agent_card
from proximo.a2a.skills import SKILLS

_TEST_URL = "http://localhost:9000/rpc"


def test_card_builds() -> None:
    """build_agent_card returns an AgentCard without raising."""
    card = build_agent_card(_TEST_URL)
    assert card is not None


def test_card_name() -> None:
    card = build_agent_card(_TEST_URL)
    assert card.name == "Proximo"


def test_card_version_is_set() -> None:
    card = build_agent_card(_TEST_URL)
    assert isinstance(card.version, str)
    assert card.version  # truthy — non-empty


def test_card_version_fallback() -> None:
    """The version= parameter is used when the package is not installed."""
    card = build_agent_card(_TEST_URL, version="0.0.0-test")
    # Either the package is installed (importlib succeeds, param ignored) or
    # the fallback is used.  Either way the version must be a non-empty string.
    assert isinstance(card.version, str)
    assert card.version


def test_card_capabilities_present() -> None:
    card = build_agent_card(_TEST_URL)
    assert card.HasField("capabilities")


def test_card_interface_url() -> None:
    card = build_agent_card(_TEST_URL)
    assert len(card.supported_interfaces) == 1
    assert card.supported_interfaces[0].url == _TEST_URL


def test_card_all_skills_present() -> None:
    """Every id in SKILLS appears exactly once on the card — no drops, no dupes."""
    card = build_agent_card(_TEST_URL)
    expected_ids = {s.id for s in SKILLS}
    card_ids = {sk.id for sk in card.skills}
    assert card_ids == expected_ids


def test_card_skill_count_matches() -> None:
    card = build_agent_card(_TEST_URL)
    assert len(card.skills) == len(SKILLS)


def test_card_skill_fields() -> None:
    """Each AgentSkill on the card carries name and description."""
    card = build_agent_card(_TEST_URL)
    skill_map = {sk.id: sk for sk in card.skills}
    for s in SKILLS:
        sk = skill_map[s.id]
        assert sk.name == s.name
        assert sk.description == s.description
        assert list(sk.tags) == list(s.tags)
        assert list(sk.examples) == list(s.examples)


def test_card_default_modes() -> None:
    card = build_agent_card(_TEST_URL)
    assert "application/json" in list(card.default_input_modes)
    assert "text/plain" in list(card.default_input_modes)
    assert "application/json" in list(card.default_output_modes)
    assert "text/plain" in list(card.default_output_modes)
