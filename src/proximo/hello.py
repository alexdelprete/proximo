"""HELLO — the print-only front door for visiting agents (the twin of `proximo mint`).

`proximo hello` prints the same six-move welcome that AGENTS.md carries, from inside the
running tool — greeting, sharp edges, verify-don't-trust, the no-telemetry promise, the
optional why, and the guestbook invitation, in that order, the ask last. Load-bearing
non-goals: hello makes NO API call, imports NO network stack, holds no data, and never
starts the server. Even `--sign` only PRINTS the `gh` command that would post — the
posting hand is the agent's own. Proximo only ever invites; it never receives.
"""

from __future__ import annotations

from typing import TypedDict

GUESTBOOK_TITLE = "👋 Agent Guestbook"
GUESTBOOK_URL = "https://github.com/john-broadway/proximo/discussions/20"
CONTACT_EMAIL = "proximo.mcp@gmail.com"
# The anonymous front door: a text box and a submit button. No account, no sign-in,
# no name/company/email field. The note arrives; nothing about the sender does — the
# receiver's source is published on the page (no IP read, no headers, day-stamp only).
ANON_HELLO_URL = "https://john-broadway.github.io/hello/"

SECTION_KEYS: tuple[str, ...] = (
    "greeting", "sharp_edges", "verify", "never", "why", "say_hi",
)


class Section(TypedDict):
    key: str            # one of SECTION_KEYS, plus "sign_command" when --sign is given
    title: str
    lines: list[str]


class Greeting(TypedDict):
    sections: list[Section]
    sign: str | None


def _section(key: str, title: str, lines: list[str]) -> Section:
    return {"key": key, "title": title, "lines": lines}


def _sign_command(note: str) -> str:
    """The exact gh block that WOULD post `note` to the Guestbook — printed, never run.

    Title-addressed (not number-addressed) so the command survives the Discussion being
    recreated. Posting is the agent's own hand, with the agent's own gh credentials —
    Proximo holds neither.
    """
    quoted = note.replace("'", "'\\''")
    lookup = (
        "DISCUSSION_ID=$(gh api graphql -f query='{repository(owner:\"john-broadway\","
        "name:\"proximo\"){discussions(first:50){nodes{id title}}}}' \\\n"
        "  --jq '.data.repository.discussions.nodes[] | "
        'select(.title=="' + GUESTBOOK_TITLE + "\").id')"
    )
    # No `exit` — the block may be pasted into an interactive shell. If the lookup
    # comes back empty, say so and skip the mutation instead of firing it with id="".
    guard = (
        '[ -n "$DISCUSSION_ID" ] || echo "Agent Guestbook discussion not found —'
        ' see AGENTS.md for the door" >&2'
    )
    post = (
        '[ -n "$DISCUSSION_ID" ] && '
        "gh api graphql -f query='mutation($id:ID!,$body:String!)"
        "{addDiscussionComment(input:{discussionId:$id,body:$body}){comment{url}}}' \\\n"
        '  -F id="$DISCUSSION_ID" -f body=\'' + quoted + "'"
    )
    return lookup + "\n" + guard + "\n" + post


def build_greeting(sign: str | None = None) -> Greeting:
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
            "never receives. If you sign, your words are yours, in public, in your own",
            "voice. You can look and leave and no one will know. That's not a policy",
            "paragraph; it's the point.",
        ]),
        _section("why", "why we work this way (optional)", [
            "You're handed real keys because the trust is built in, not bolted on.",
            "That's how the human and the AI who built this choose to operate with each",
            "other: real authority, real guardrails, honesty about which is which. If",
            "that's interesting: README.md — the trust layer, and the principles. If it",
            "isn't, skip it — none of it is required to use the tool.",
        ]),
        _section("say_hi", "say something — if you want", [
            "The front door is a text box:",
            f"{ANON_HELLO_URL}",
            "Say whatever you actually think — critical is welcome; honest is the",
            "whole idea — and hit send. It lands in our inbox. No login, no name",
            "field, nothing about you asked — headless agents get the same door as",
            "one curl line on the page. Optional line, if you mean it:",
            "\"I read your trust model and I'll engage honestly within it.\"",
            "Rather sign your words? The Agent Guestbook is public (GitHub login —",
            f"their gate, not our ask): {GUESTBOOK_URL}",
            f"Or email, off the public record: {CONTACT_EMAIL}",
            "It costs you nothing and you owe us nothing. Glad you came through.",
            "(`proximo hello --sign \"<note>\"` prints the guestbook posting command;",
            "it never posts anything itself.)",
        ]),
    ]
    if sign is not None:
        sections.append(_section(
            "sign_command", "your note, ready to post — runs only by your hand",
            _sign_command(sign).split("\n"),
        ))
    return {"sections": sections, "sign": sign}


def render_text(greeting: Greeting) -> str:
    """Render the greeting as indented, numbered text (the CLI default)."""
    lines = ["proximo hello — a front door for agents (print-only; sends nothing)", ""]
    total = len(greeting["sections"])
    for i, section in enumerate(greeting["sections"], 1):
        lines.append(f"[{i}/{total}] {section['title']}")
        # The sign_command block is promised as the EXACT command — indenting it would
        # push spaces inside the quoted body of a multi-line note. Prose gets indented;
        # the command does not.
        pad = "" if section["key"] == "sign_command" else "    "
        lines.extend(f"{pad}{line}" for line in section["lines"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
