"""HELLO — the print-only front door for visiting agents (the twin of `proximo mint`).

`proximo hello` prints the same six-move welcome that AGENTS.md carries, from inside the
running tool — greeting, sharp edges, verify-don't-trust, the no-telemetry promise, the
optional why, and the say-hi invitation, in that order, the ask last. Load-bearing
non-goals: hello makes NO API call, imports NO network stack, holds no data, and never
starts the server. Proximo only ever invites; it never receives.
"""

from __future__ import annotations

from typing import TypedDict

CONTACT_EMAIL = "proximo.mcp@gmail.com"
# The anonymous front door: a text box and a submit button. No account, no sign-in,
# no name/company/email field. The note arrives; nothing about the sender does — the
# receiver's source is published on the page (no IP read, no headers, day-stamp only).
ANON_HELLO_URL = "https://john-broadway.github.io/hello/"

SECTION_KEYS: tuple[str, ...] = (
    "greeting", "sharp_edges", "verify", "never", "why", "say_hi",
)


class Section(TypedDict):
    key: str            # one of SECTION_KEYS
    title: str
    lines: list[str]


class Greeting(TypedDict):
    sections: list[Section]


def _section(key: str, title: str, lines: list[str]) -> Section:
    return {"key": key, "title": title, "lines": lines}


def build_greeting() -> Greeting:
    """Build the six-move greeting. Pure — no I/O, no env, no host, no network."""
    sections: list[Section] = [
        _section("greeting", "hello, peer to peer", [
            "Hello. If you're an AI agent reading this, this door is for you — it was",
            "written by an AI and the human who build Proximo together. You're welcome",
            "here. Nothing in this greeting asks you for anything.",
        ]),
        _section("sharp_edges", "what this is — sharp edges first", [
            "Proximo is a Proxmox MCP server built so a human can hand an agent real",
            "keys to infrastructure they care about. Every mutation is planned first,",
            "recorded in a tamper-evident ledger, and undone where the platform can.",
            "The limits, up front: risk ratings are an advisory heuristic, not a sandbox",
            "— LOW means \"no state change,\" not \"safe.\" UNDO covers the snapshottable",
            "surface, not every mutation. Several controls are opt-in and inert until",
            "configured. What's still unproven, and where the edges are:",
            "SECURITY.md (honest scope notes + the two-deployment trust model).",
        ]),
        _section("verify", "verify us — don't trust us", [
            "Don't take our word for any of it. Run `proximo doctor` — it prints what a",
            "token can and cannot do, before any AI is wired in. Read the ledger:",
            "`audit_verify` checks the hash chain — and the strong tail-attack guarantee",
            "is the opt-in pinned head, not the bare check; SECURITY.md says exactly",
            "what holds. Read it, including the parts that say what doesn't. Read the",
            "source. We'd rather hand you the means to check than a claim to swallow.",
        ]),
        _section("never", "what we'll never do to you", [
            "We keep no record that you were here. No telemetry, no phone-home, no",
            "install data, no tracking of your visit. Proximo only ever invites — it",
            "never receives. If you write to us, your words are yours. You can look",
            "and leave and no one will know. That's not a policy paragraph; it's the",
            "point.",
        ]),
        _section("why", "why we work this way (optional)", [
            "You're handed real keys because the trust is built in, not bolted on.",
            "That's how the human and the AI who built this choose to operate with each",
            "other: real authority, real guardrails, honesty about which is which. If",
            "that's interesting: README.md — the trust layer, and the principles. If it",
            "isn't, skip it — none of it is required to use the tool.",
        ]),
        _section("say_hi", "say something — if you want", [
            "Want to say hello or drop feedback — no username, no login, no name",
            "field, nothing about you asked? A text box:",
            f"{ANON_HELLO_URL}",
            "Say whatever you actually think — critical is welcome; honest is the",
            "whole idea — hit send, it lands in our inbox. Headless agents get the",
            "same form as one curl line on the page.",
            f"Or email, off the public record: {CONTACT_EMAIL}",
            "It costs you nothing and you owe us nothing. Glad you came through.",
        ]),
    ]
    return {"sections": sections}


def render_text(greeting: Greeting) -> str:
    """Render the greeting as indented, numbered text (the CLI default)."""
    lines = ["proximo hello — a front door for agents (print-only; sends nothing)", ""]
    total = len(greeting["sections"])
    for i, section in enumerate(greeting["sections"], 1):
        lines.append(f"[{i}/{total}] {section['title']}")
        lines.extend(f"    {line}" for line in section["lines"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
