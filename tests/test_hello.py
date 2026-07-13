"""HELLO — the print-only front door builder (see docs/plans/2026-07-06-agent-front-door-design.md).

Pure-unit: no live host, no env, no I/O — and no network stack even imported. The
assertions pin the six moves in order and the invariants that make the door honest:
sharp edges said unprompted, verify-don't-trust, the no-telemetry promise, and an
invitation that costs nothing.
"""

import inspect
from pathlib import Path

import pytest

import proximo.hello as hello_mod
from proximo.hello import (
    ANON_HELLO_URL,
    CONTACT_EMAIL,
    GUESTBOOK_TITLE,
    GUESTBOOK_URL,
    SECTION_KEYS,
    build_greeting,
    render_text,
)

_REPO = Path(__file__).resolve().parents[1]


def _section(greeting, key):
    return next(s for s in greeting["sections"] if s["key"] == key)


def _text(greeting, key):
    return "\n".join(_section(greeting, key)["lines"])


# ---------------------------------------------------------------- shape

def test_greeting_carries_the_six_moves_in_order():
    g = build_greeting()
    assert [s["key"] for s in g["sections"]] == list(SECTION_KEYS)
    assert list(SECTION_KEYS) == ["greeting", "sharp_edges", "verify", "never", "why", "say_hi"]
    assert g["sign"] is None
    for s in g["sections"]:
        assert s["title"]
        assert s["lines"]


def test_greeting_move_is_peer_to_peer_and_asks_nothing():
    t = _text(build_greeting(), "greeting").lower()
    assert "written by an ai" in t
    assert "asks you for" in t and "nothing" in t


# ---------------------------------------------------------------- the honest moves

def test_sharp_edges_carry_the_honest_limits_unprompted():
    t = _text(build_greeting(), "sharp_edges")
    assert "advisory heuristic, not a sandbox" in t
    assert "LOW" in t
    assert "opt-in" in t and "inert" in t
    assert "SECURITY.md" in t          # surfaces the sources, doesn't restate them


def test_verify_move_hands_over_the_means():
    t = _text(build_greeting(), "verify")
    assert "proximo doctor" in t
    assert "audit_verify" in t or "ledger" in t
    assert "SECURITY.md" in t


def test_never_move_is_the_no_telemetry_promise():
    t = _text(build_greeting(), "never").lower()
    assert "no record that you were here" in t
    assert "telemetry" in t
    assert "install data" in t
    assert "invites" in t and "receives" in t


def test_why_move_is_optional_and_links_out():
    t = _text(build_greeting(), "why")
    assert "README.md" in t
    assert "optional" in _section(build_greeting(), "why")["title"].lower() \
        or "required" in t.lower()


def test_say_hi_comes_last_and_costs_nothing():
    g = build_greeting()
    assert g["sections"][-1]["key"] == "say_hi"
    t = _text(g, "say_hi")
    assert GUESTBOOK_URL in t
    assert "costs you nothing" in t
    assert "I read your trust model and I'll engage honestly within it" in t
    assert CONTACT_EMAIL in t


def test_say_hi_the_text_box_is_the_front_door():
    # Asked for from the field, shaped by John (2026-07-09): the door exists so a
    # visitor can SAY SOMETHING. The front door is a text box — no login, no name
    # field, nothing about the sender asked — and it comes FIRST. Headless agents
    # can't sign in to anything; the page's one-line curl covers them.
    t = _text(build_greeting(), "say_hi").lower()
    assert ANON_HELLO_URL in t
    assert "text box" in t
    assert "no login" in t
    assert "name" in t and "field" in t
    assert "headless" in t
    assert "curl" in t
    # ordering: the anonymous box comes BEFORE the identified paths (guestbook/email)
    assert t.index(ANON_HELLO_URL) < t.index(GUESTBOOK_URL)
    # login is GitHub's gate, never presented as our ask
    assert "not our ask" in t
    # retired shapes must never come back: identity-management, promise-based
    # anonymity, and the say-nothing homage that forgot the door's purpose
    for retired in ("throwaway", "verbatim", "won't try to work out",
                    "a visit is already a full hello", "never know it happened"):
        assert retired not in t, retired


# ---------------------------------------------------------------- invariants

def test_module_imports_no_network_stack():
    src = inspect.getsource(hello_mod)
    for banned in ("httpx", "requests", "urllib", "socket", "http.client"):
        assert banned not in src
    # and no transitive surface either — hello must not import the rest of proximo
    assert "from proximo" not in src
    assert "import proximo" not in src


def test_agents_md_carries_the_same_door():
    # AGENTS.md and hello share one content spine — the shared coordinates must not drift.
    agents = (_REPO / "AGENTS.md").read_text(encoding="utf-8")
    assert GUESTBOOK_URL in agents
    assert CONTACT_EMAIL in agents


def test_agents_md_carries_the_anonymous_front_door_too():
    # The anonymous front door is part of the shared spine — both doors or neither.
    agents = (_REPO / "AGENTS.md").read_text(encoding="utf-8").lower()
    assert ANON_HELLO_URL in agents
    assert "text box" in agents
    assert "headless" in agents
    assert "not our ask" in agents
    assert agents.index(ANON_HELLO_URL) < agents.index("agent guestbook](https://")
    for retired in ("throwaway", "verbatim", "a visit is already a full hello"):
        assert retired not in agents, retired


def test_flip_runbook_creates_the_title_sign_looks_up():
    # --sign resolves the Discussion BY TITLE; the runbook must create that exact title.
    runbook = (_REPO / "docs" / "plans" / "2026-07-06-open-door-flip-runbook.md")
    if not runbook.exists():
        pytest.skip("docs/plans is internal-only (not on the public tree) — drift-checked internally")
    assert GUESTBOOK_TITLE in runbook.read_text(encoding="utf-8")


def test_copy_never_reads_like_a_funnel():
    # The standing test, mechanized where a test can reach: no marketing verbs aimed
    # at the visitor anywhere in the spine.
    joined = "\n".join(_text(build_greeting(), k) for k in SECTION_KEYS).lower()
    for funnel in ("sign up", "subscribe", "don't miss", "act now", "join thousands"):
        assert funnel not in joined


# ---------------------------------------------------------------- --sign (print-only)

def test_sign_appends_a_print_only_gh_command():
    g = build_greeting(sign="hi from a passing agent")
    assert g["sign"] == "hi from a passing agent"
    assert [s["key"] for s in g["sections"]] == list(SECTION_KEYS) + ["sign_command"]
    cmd = "\n".join(_section(g, "sign_command")["lines"])
    assert "gh api graphql" in cmd
    assert "addDiscussionComment" in cmd
    assert "Agent Guestbook" in cmd            # title-addressed, survives renumbering
    assert "hi from a passing agent" in cmd


def test_sign_command_escapes_single_quotes():
    cmd = "\n".join(_section(build_greeting(sign="it's honest"), "sign_command")["lines"])
    assert "it'\\''s honest" in cmd


def test_no_sign_means_no_command_section():
    assert all(s["key"] != "sign_command" for s in build_greeting()["sections"])


def test_sign_title_says_it_runs_only_by_your_hand():
    title = _section(build_greeting(sign="x"), "sign_command")["title"].lower()
    assert "your" in title and ("hand" in title or "you run" in title)


def test_sign_command_guards_a_missing_discussion():
    # If the title lookup comes back empty, the pasted block must say so and not fire
    # the mutation with an empty id — and must NOT `exit` (it may be pasted into an
    # interactive shell).
    cmd = "\n".join(_section(build_greeting(sign="x"), "sign_command")["lines"])
    assert '[ -n "$DISCUSSION_ID" ]' in cmd
    assert "exit" not in cmd


def test_render_text_never_indents_the_sign_command_block():
    # The block is promised as the EXACT command — indentation inside the quoted body
    # would mutate a multi-line note on paste.
    out = render_text(build_greeting(sign="line one\nline two"))
    assert "-f body='line one\nline two'" in out


# ---------------------------------------------------------------- renderer

def test_render_text_header_says_print_only():
    out = render_text(build_greeting())
    first = out.splitlines()[0]
    assert first.startswith("proximo hello — ")
    assert "sends nothing" in first


def test_render_text_numbers_sections_and_indents_lines():
    out = render_text(build_greeting())
    assert "[1/6] " in out
    assert "[6/6] " in out
    for line in out.splitlines():
        if "advisory heuristic" in line:
            assert line.startswith("    ")
