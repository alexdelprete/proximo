"""Contract tests for the Proximo A2A skill registry and PLAN-by-default guard.

These tests NEVER touch the server, the A2A SDK, or the network.  The skill
registry (``proximo.a2a.skills``) is pure Python with no a2a-sdk import, so
every test here runs unconditionally — even in environments where the a2a extras
are absent.

The ``test_build_app_*`` tests at the bottom require:
  1. The a2a SDK (``pytest.importorskip("a2a", exc_type=ModuleNotFoundError)``).
  2. The sibling executor module (``pytest.importorskip("proximo.a2a.executor", exc_type=ModuleNotFoundError)``).

If either is absent the tests are *skipped* (not failed).

ASSUMPTION: ``ProximoAgentExecutor()`` takes no constructor arguments.  That is
the executor-agent's contract; it is not verifiable here.
"""

from __future__ import annotations

import pytest

from proximo.a2a.skills import (
    EXCLUDED_FROM_SLICE,
    SKILLS,
    SKILLS_BY_ID,
    A2AParamError,
    _type_ok,
    validate_and_build,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MUTATING_SKILL = next(s for s in SKILLS if s.mutating)
_READ_SKILL = next(s for s in SKILLS if not s.mutating)

# A mutating skill that has at least one required param (for the required-missing test).
_MUTATING_WITH_REQUIRED = next(
    s for s in SKILLS if s.mutating and s.required_params
)

# Required params with valid dummy values for _MUTATING_WITH_REQUIRED.
def _required_params(skill) -> dict:
    """Return a minimal set of valid required params for *skill*."""
    out = {}
    for p in skill.params:
        if not p.required:
            continue
        if p.type == "string":
            out[p.name] = "dummy"
        elif p.type == "integer":
            out[p.name] = 1
        elif p.type == "boolean":
            out[p.name] = True
        elif p.type == "object":
            out[p.name] = {}
        elif p.type == "array":
            out[p.name] = []
    return out


# ---------------------------------------------------------------------------
# Structural invariants
# ---------------------------------------------------------------------------


def test_skills_ids_unique() -> None:
    """Every skill must have a unique id."""
    ids = [s.id for s in SKILLS]
    assert len(ids) == len(set(ids)), "duplicate skill ids"


def test_skills_by_id_index_matches() -> None:
    """SKILLS_BY_ID must be a 1-to-1 index into SKILLS."""
    assert set(SKILLS_BY_ID) == {s.id for s in SKILLS}
    for skill in SKILLS:
        assert SKILLS_BY_ID[skill.id] is skill


def test_every_skill_tool_is_callable() -> None:
    """Every skill's .tool must be callable (points at a real server function)."""
    for skill in SKILLS:
        assert callable(skill.tool), f"skill '{skill.id}' .tool is not callable"


def test_read_skills_have_mutating_false() -> None:
    """Skills without mutations must have mutating=False (no PLAN-by-default bypass)."""
    for skill in SKILLS:
        if "read" in skill.tags or "diagnostics" in skill.tags:
            assert not skill.mutating, (
                f"skill '{skill.id}' has a read/diagnostics tag but mutating=True"
            )


def test_mutating_skills_have_mutating_true() -> None:
    """Skills tagged 'mutation' must have mutating=True."""
    for skill in SKILLS:
        if "mutation" in skill.tags:
            assert skill.mutating, (
                f"skill '{skill.id}' is tagged 'mutation' but mutating=False"
            )


def test_no_excluded_function_in_slice() -> None:
    """None of the EXCLUDED_FROM_SLICE function names may appear in the slice."""
    exposed = {s.tool.__name__ for s in SKILLS}
    leak = exposed & set(EXCLUDED_FROM_SLICE)
    assert not leak, f"excluded tools leaked into the A2A slice: {sorted(leak)}"


# ---------------------------------------------------------------------------
# validate_and_build — PLAN-by-default guard matrix
# ---------------------------------------------------------------------------


class TestValidateAndBuild:
    """Verify the PLAN-by-default guard in validate_and_build."""

    # --- confirm omitted ---

    def test_no_confirm_for_mutating_omits_confirm_key(self) -> None:
        """Without confirm, kwargs must not contain 'confirm' at all."""
        kwargs = validate_and_build(_MUTATING_SKILL, _required_params(_MUTATING_SKILL))
        assert "confirm" not in kwargs

    def test_no_confirm_for_read_skill_succeeds(self) -> None:
        """Read-only skills work fine without confirm."""
        kwargs = validate_and_build(_READ_SKILL, None)
        assert "confirm" not in kwargs

    # --- confirm=True ---

    def test_confirm_true_is_passed_through_for_mutating(self) -> None:
        """confirm=true (bool) must be forwarded for mutating skills."""
        params = {**_required_params(_MUTATING_SKILL), "confirm": True}
        kwargs = validate_and_build(_MUTATING_SKILL, params)
        assert kwargs.get("confirm") is True

    # --- confirm=False ---

    def test_confirm_false_is_dropped_for_mutating(self) -> None:
        """confirm=false must NOT be forwarded — dry-run is the default."""
        params = {**_required_params(_MUTATING_SKILL), "confirm": False}
        kwargs = validate_and_build(_MUTATING_SKILL, params)
        assert "confirm" not in kwargs

    # --- confirm on read skill ---

    def test_confirm_on_read_skill_raises(self) -> None:
        """Passing confirm to a read-only skill must raise A2AParamError."""
        with pytest.raises(A2AParamError, match="read-only"):
            validate_and_build(_READ_SKILL, {"confirm": True})

    # --- confirm="true" (wrong type) ---

    def test_confirm_string_true_raises(self) -> None:
        """confirm must be a real bool; the string 'true' must be rejected."""
        params = {**_required_params(_MUTATING_SKILL), "confirm": "true"}
        with pytest.raises(A2AParamError, match="boolean"):
            validate_and_build(_MUTATING_SKILL, params)

    def test_confirm_integer_one_raises(self) -> None:
        """confirm must be a real bool; integer 1 must be rejected."""
        params = {**_required_params(_MUTATING_SKILL), "confirm": 1}
        with pytest.raises(A2AParamError, match="boolean"):
            validate_and_build(_MUTATING_SKILL, params)

    # --- unknown params ---

    def test_unknown_param_raises(self) -> None:
        """An unrecognised parameter must be rejected (fail-closed)."""
        params = {**_required_params(_MUTATING_SKILL), "bogus_key": "val"}
        with pytest.raises(A2AParamError, match="unknown"):
            validate_and_build(_MUTATING_SKILL, params)

    def test_unknown_param_on_read_skill_raises(self) -> None:
        """Unknown params are rejected for read-only skills too."""
        with pytest.raises(A2AParamError, match="unknown"):
            validate_and_build(_READ_SKILL, {"not_a_param": 99})

    # --- missing required params ---

    def test_missing_required_param_raises(self) -> None:
        """Omitting a required param must raise A2AParamError."""
        with pytest.raises(A2AParamError, match="missing"):
            validate_and_build(_MUTATING_WITH_REQUIRED, {})

    def test_missing_required_param_message_names_param(self) -> None:
        """The error message must name the missing parameter(s)."""
        first_required = _MUTATING_WITH_REQUIRED.required_params[0]
        with pytest.raises(A2AParamError, match=first_required):
            validate_and_build(_MUTATING_WITH_REQUIRED, {})

    # --- type mismatches ---

    def test_wrong_type_for_string_param_raises(self) -> None:
        """Passing an integer where a string is declared must raise A2AParamError."""
        # Find a skill with a required string param.
        skill_with_str = next(
            (s for s in SKILLS if any(p.required and p.type == "string" for p in s.params)),
            None,
        )
        if skill_with_str is None:
            pytest.skip("no skill with a required string param found")
        str_param = next(p for p in skill_with_str.params if p.required and p.type == "string")
        bad_params = {**_required_params(skill_with_str), str_param.name: 42}
        with pytest.raises(A2AParamError):
            validate_and_build(skill_with_str, bad_params)

    def test_bool_rejected_as_integer(self) -> None:
        """A boolean value must NOT satisfy an 'integer' typed param (bool is a subclass of int)."""
        assert not _type_ok(True, "integer")
        assert not _type_ok(False, "integer")
        assert _type_ok(1, "integer")

    # --- None / empty raw_params ---

    def test_none_raw_params_is_valid_for_no_required_params(self) -> None:
        """validate_and_build(skill, None) must work for skills with no required params."""
        no_req = next((s for s in SKILLS if not s.required_params), None)
        if no_req is None:
            pytest.skip("no skill with zero required params found")
        kwargs = validate_and_build(no_req, None)
        assert isinstance(kwargs, dict)

    def test_empty_dict_is_valid_for_no_required_params(self) -> None:
        """validate_and_build(skill, {}) must work for skills with no required params."""
        no_req = next((s for s in SKILLS if not s.required_params), None)
        if no_req is None:
            pytest.skip("no skill with zero required params found")
        kwargs = validate_and_build(no_req, {})
        assert isinstance(kwargs, dict)


# ---------------------------------------------------------------------------
# build_app — requires a2a SDK + sibling executor (skipped if absent)
# ---------------------------------------------------------------------------


def test_build_app_importable_and_returns_starlette() -> None:
    """build_app() must import cleanly and return a Starlette instance.

    Skipped if the a2a SDK extras are not installed OR if the sibling
    ``executor.py`` (the other agent's deliverable) is not yet present.
    """
    pytest.importorskip("a2a", exc_type=ModuleNotFoundError)
    pytest.importorskip("proximo.a2a.executor", exc_type=ModuleNotFoundError)

    from starlette.applications import Starlette  # noqa: PLC0415

    from proximo.a2a.app import build_app  # noqa: PLC0415

    app = build_app("http://127.0.0.1:41241/")
    assert isinstance(app, Starlette)


def test_build_app_default_url() -> None:
    """build_app() with no args must also succeed (uses default URL)."""
    pytest.importorskip("a2a", exc_type=ModuleNotFoundError)
    pytest.importorskip("proximo.a2a.executor", exc_type=ModuleNotFoundError)

    from starlette.applications import Starlette  # noqa: PLC0415

    from proximo.a2a.app import build_app  # noqa: PLC0415

    app = build_app()
    assert isinstance(app, Starlette)
