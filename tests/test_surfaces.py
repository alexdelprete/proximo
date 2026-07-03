"""PROXIMO_SURFACES — opt-in registration scoping (context hygiene + surface reduction).

Unset/empty => all tools registered, zero behavior change (the house opt-in contract).
Set => only the named surfaces' tools stay in the MCP registry; everything else is
removed BEFORE serving, so unpicked planes never reach the client's context at all
(a structural gate, not a runtime refusal). `audit_verify` is always kept — PROVE is
never scopeable away. An unknown surface name refuses startup loudly (fail-closed:
a typo must never silently serve a different surface than the operator believes).
"""
from __future__ import annotations

import pytest

from proximo import server
from proximo.server import SURFACES, surface_keep

REGISTRY = set(server.mcp._tool_manager._tools)  # read-only snapshot of the live registry


def test_unset_and_blank_are_inert():
    assert surface_keep(REGISTRY, None) == REGISTRY
    assert surface_keep(REGISTRY, "") == REGISTRY
    assert surface_keep(REGISTRY, "   ") == REGISTRY


def test_single_surface_keeps_only_that_plane_plus_audit():
    keep = surface_keep(REGISTRY, "pbs")
    assert keep == {n for n in REGISTRY if n.startswith("pbs_")} | {"audit_verify"}


def test_multi_surface_union():
    keep = surface_keep(REGISTRY, "pbs, pmg")
    assert {n for n in keep if n != "audit_verify"} == {
        n for n in REGISTRY if n.startswith(("pbs_", "pmg_"))
    }


def test_exec_surface_is_the_ct_tools():
    keep = surface_keep(REGISTRY, "exec")
    assert keep == {"ct_exec", "ct_psql", "ct_logs", "ct_diagnose", "audit_verify"}


def test_audit_verify_always_kept():
    for spec in ("pve", "pbs", "exec", "pve,pbs,pmg,pdm,exec"):
        assert "audit_verify" in surface_keep(REGISTRY, spec)


def test_unknown_surface_refuses_loudly():
    with pytest.raises(ValueError, match="PROXIMO_SURFACES"):
        surface_keep(REGISTRY, "pve,exce")  # the typo that must never pass silently


def test_spec_is_case_insensitive_and_whitespace_tolerant():
    assert surface_keep(REGISTRY, " PVE ,Exec") == surface_keep(REGISTRY, "pve,exec")


def test_every_registered_tool_belongs_to_exactly_one_surface():
    """Completeness guard (same pattern as the TAINT classification test): a new tool
    whose prefix matches no surface would silently survive every filter — fail CI instead."""
    prefixes = tuple(p for pl in SURFACES.values() for p in pl)
    orphans = [n for n in REGISTRY if not n.startswith(prefixes) and n != "audit_verify"]
    assert not orphans, f"tools outside every surface (extend SURFACES or _ALWAYS): {orphans}"
    multi = [n for n in REGISTRY if sum(n.startswith(p) for p in prefixes) > 1]
    assert not multi, f"tools matching more than one surface: {multi}"


def test_apply_surfaces_prunes_a_registry(monkeypatch):
    """_apply_surfaces drives mcp.remove_tool from the env spec — proven on a fake."""
    removed: list[str] = []

    class _FakeTM:
        _tools = {n: None for n in ("pve_doctor", "pbs_prune", "ct_exec", "audit_verify")}

    class _FakeMCP:
        _tool_manager = _FakeTM()

        def remove_tool(self, name: str) -> None:
            removed.append(name)

    monkeypatch.setenv("PROXIMO_SURFACES", "pve")
    server._apply_surfaces(_FakeMCP())
    assert sorted(removed) == ["ct_exec", "pbs_prune"]


def test_apply_surfaces_unset_touches_nothing(monkeypatch):
    monkeypatch.delenv("PROXIMO_SURFACES", raising=False)

    class _FakeMCP:
        def remove_tool(self, name: str) -> None:  # pragma: no cover — must not be called
            raise AssertionError("remove_tool called with PROXIMO_SURFACES unset")

    server._apply_surfaces(_FakeMCP())
