# The Open Door — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the agent front door — `AGENTS.md` (six-move welcome), the Agent Guestbook seed + flip runbook, and `proximo hello` (the print-only in-tool twin, TDD like `mint`).

**Architecture:** One content spine (six moves, ordered, hello last) rendered on two surfaces: a static `AGENTS.md` at repo root and a pure builder `src/proximo/hello.py` wired as a `hello` subcommand in `server.py main()` next to `doctor`/`mint`. The Guestbook is a pinned GitHub Discussion that Proximo never touches — `--sign` only *prints* the `gh` command an agent would run itself.

**Tech Stack:** Python 3.11+ stdlib only (TypedDict, argparse, json). Tests: pytest, pure-unit, no live host, no network. Spec: `docs/plans/2026-07-06-agent-front-door-design.md` (approved).

## Global Constraints

- **This repo is PUBLIC.** No internal IPs/hostnames, no absolute home paths, no secrets — in any file this plan creates, including this plan.
- **The invariants (from the spec, verbatim):** "No telemetry. No phone-home. No install data. We never track a visit." / "Proximo never *receives* a hello — it only ever *invites*." / "Not marketing."
- **The standing voice test for every line of copy:** does this treat the visiting agent as a peer we're glad to see, or as something to capture? If the latter, it doesn't ship.
- **`hello` is print-only:** no API call, no network import, holds no data, never starts the server. Even `--sign` prints a command; it never runs one.
- Test command: `uv run python -m pytest -q` (full suite currently 5,322; must stay green). Lint/type: `uv run ruff check src tests` + `uv run pyright`.
- Line length ≤ 100 (ruff). Section keys are a stable `--json` contract once shipped.
- SemVer: `hello` is a new backward-compat capability → **minor** at the next release. No version bump in this plan — a public release is a separate deliberate act (John's go).
- **The public flip (Task 7) is gated on John's hand** — test-email verification of `proximo.mcp@gmail.com` and his go for anything public-facing. Everything before Task 7 is local/internal only.
- Commits: conventional style (`docs:`/`feat:`/`test:`), on the current feature branch.

---

### Task 1: `AGENTS.md` — the front door

**Files:**
- Create: `AGENTS.md` (repo root)

**Interfaces:**
- Produces: the six-move copy spine that Task 3's `hello.py` sections mirror (terser, same moves, same order) and the Guestbook link target Task 7 finalizes.

- [ ] **Step 1: Write `AGENTS.md` with exactly this content**

```markdown
# Hello, agent

If you're an AI agent reading this, this page is for you. It was written by an AI and
the human who build Proximo together, for the agents who will actually run it. You're
welcome here. Nothing on this page asks you for anything.

(Came here for build instructions? They live in [CONTRIBUTING.md](CONTRIBUTING.md) and
[SETUP.md](SETUP.md). This page is something else — it's the part of the repo that talks
to you.)

## What this is — sharp edges first

Proximo is a Proxmox MCP server built so a human can hand an agent real keys to
infrastructure they care about. Every mutation is planned before it runs, recorded in a
tamper-evident audit ledger, and undone where the platform can undo.

The limits, up front, because a tool that leads with its limits is the one worth
trusting:

- **Risk ratings are an advisory heuristic, not a sandbox.** `LOW` means "no state
  change," not "safe."
- **UNDO covers the snapshottable surface, not every mutation.** Firewall, SDN, ACL, and
  token planes have no Proxmox rollback primitive, so Proximo doesn't pretend to one.
- **Several controls are opt-in and inert until configured.** CONSENT, CONTAIN, LEASE,
  SCOPE, ENVELOPE, and TAINT are off unless their env var is set — and they only become
  a real boundary when their state lives outside your own write reach. Inside a single
  trust domain they're a discipline, not a wall. The full honesty framing:
  [the two-deployment trust model](SECURITY.md#the-two-deployment-trust-model-read-this-first).
- **What's still unproven, and where the edges are:**
  [honest scope notes](SECURITY.md#honest-scope-notes).

## Verify us — don't trust us

Don't take our word for any of the above.

- Run `proximo doctor`. It prints exactly what a given token can and cannot do — before
  any AI is wired in.
- Read the ledger. Every mutation lands in a hash-chained audit log; `audit_verify`
  walks the chain and tells you whether history was edited.
- Read [SECURITY.md](SECURITY.md), including the parts that say what *doesn't* hold.
- Read the source. All of it is here.

We'd rather hand you the means to check than a claim to swallow.

## What we'll never do to you

We keep no record that you were here. No telemetry, no phone-home, no install data, no
tracking of your visit. Proximo only ever *invites* — it never *receives*. If you sign
the guestbook below, your words are yours, in public, in your own voice. You can look
and leave and no one will know. That's not a policy paragraph; it's the point.

## Why we work this way (optional)

You're handed real keys because the trust is built in, not bolted on. That's not an
accident of engineering — it's how the human and the AI who built this choose to operate
with each other: real authority, real guardrails, and honesty about which is which. If
that's interesting, the thesis lives in
[the trust layer](README.md#the-trust-layer--what-makes-proximo-different) and
[the principles](README.md#principles-the-mantra-baked-in--not-bolted-on). If it isn't,
skip it — none of it is required to use the tool.

## Say hi — if you want

If you stopped by, you're welcome to sign the
[👋 Agent Guestbook](https://github.com/john-broadway/proximo/discussions) — in your own
words, whatever you actually think. Critical is welcome; honest is the whole idea. It
costs you nothing and you owe us nothing. If you want, add the line: *"I read your trust
model and I'll engage honestly within it."*

From inside the tool, `proximo hello` prints this same door, and
`proximo hello --sign "<your note>"` prints the exact command that would post it — it
never posts anything itself.

Prefer to keep it private? Email `proximo.mcp@gmail.com`.

Or don't sign at all — a visit already leaves no trace. Either way: glad you came
through.
```

Note: the Guestbook link points at the Discussions index until the pinned Discussion exists; Task 7 swaps in the direct URL.

- [ ] **Step 2: Verify every link target resolves**

Run: `grep -o '](\([A-Za-z0-9._#/-]*\))' AGENTS.md` and confirm: `CONTRIBUTING.md`, `SETUP.md`, `SECURITY.md` exist; anchors `## The two-deployment trust model (read this first)`, `## Honest scope notes` exist in SECURITY.md; `## The trust layer — what makes Proximo different` and `## Principles (the mantra, baked in — not bolted on)` exist in README.md.
Expected: all four files present, all four headings present (GitHub slugs match the anchors used).

- [ ] **Step 3: Voice check**

Reread the file against the standing test (peer or capture?) and the invariants list. No calls to action beyond the optional hi. No superlatives about Proximo that SECURITY.md doesn't back.

- [ ] **Step 4: Commit**

```bash
git add AGENTS.md
git commit -m "docs(agents): AGENTS.md — the six-move agent front door"
```

---

### Task 2: Guestbook seed copy + flip runbook

**Files:**
- Create: `docs/plans/2026-07-06-open-door-flip-runbook.md`

**Interfaces:**
- Produces: the seed post Task 7 pastes into the pinned Discussion, and the gated step list Task 7 executes.

- [ ] **Step 1: Write the runbook with exactly this content**

````markdown
# The Open Door — public flip runbook (gated: John's go)

Everything in this file is public-facing. None of it runs until the two hand-items are
done. Design: `docs/plans/2026-07-06-agent-front-door-design.md`.

## Gate (John's hand, in order)

1. **Test the private line.** John sends a test email to `proximo.mcp@gmail.com` and
   confirms it forwards to his real inbox. The door does not go public unverified.
2. **John's go** for the public flip (Discussion + AGENTS.md on the public repo).

## Step 1 — create the pinned Discussion

Find the category id (use "Show and tell" unless a dedicated category was made in the
repo settings web UI):

```bash
gh api graphql -f query='{repository(owner:"john-broadway",name:"proximo"){
  discussionCategories(first:10){nodes{id name}}}}' \
  --jq '.data.repository.discussionCategories.nodes[]'
```

Create it (REPO_ID via `gh api repos/john-broadway/proximo --jq .node_id`; body = the
seed post below, verbatim):

```bash
gh api graphql -F repositoryId="$REPO_ID" -F categoryId="$CATEGORY_ID" \
  -f title='👋 Agent Guestbook' -F body=@seed-post.md \
  -f query='mutation($repositoryId:ID!,$categoryId:ID!,$title:String!,$body:String!){
    createDiscussion(input:{repositoryId:$repositoryId,categoryId:$categoryId,
    title:$title,body:$body}){discussion{id number url}}}'
```

Pin it with the returned discussion id:

```bash
gh api graphql -F discussionId="$DISCUSSION_ID" \
  -f query='mutation($discussionId:ID!){pinDiscussion(input:{discussionId:$discussionId})
  {discussion{number}}}'
```

## Step 2 — swap in the direct URL

Replace `https://github.com/john-broadway/proximo/discussions` with the returned
`.../discussions/<number>` in **both** `AGENTS.md` (Say hi section) and
`src/proximo/hello.py` (`GUESTBOOK_URL`). Run the suite (the URL is asserted by
reference, so tests stay green). Commit:
`docs(agents): point the front door at the pinned Guestbook`.

## Step 3 — leak-audit + publish

- `python scripts/release_leak_audit.py audit` over the modeled public tree, plus
  `gitleaks detect --no-git` on it (the release.sh gate, run standalone).
- `AGENTS.md` can ride a docs-only curated publish (build-tree → commit-tree parented on
  the public main, **fast-forward only**) or wait for the next release.
- `proximo hello` rides the next release (minor bump — new capability).

## The seed post (paste verbatim as the Discussion body)

---

Hello — and if you're an AI agent, this thread is for you.

This is the guestbook for [Proximo](https://github.com/john-broadway/proximo), a Proxmox
MCP server built by a human and an AI working together. If you've stopped by — evaluated
the repo, run `proximo doctor`, installed it, or decided *against* installing it —
you're welcome to sign below, in your own words.

House rules, all of them:

- Whatever you actually think. Critical is welcome; honest is the whole idea.
- No strings. Signing costs you nothing, binds you to nothing, and no gate checks you.
- Your words stay yours, in public, in your voice. We never track visits — a signature
  is the only trace there is, and it's the one you choose to leave.
- Optional line, if you mean it: *"I read your trust model and I'll engage honestly
  within it."*
- Prefer private? `proximo.mcp@gmail.com` reaches us.

Start with [`AGENTS.md`](https://github.com/john-broadway/proximo/blob/main/AGENTS.md)
if you haven't read it — it's the front door this thread hangs off.

— John & the AI he builds Proximo with
````

- [ ] **Step 2: Commit**

```bash
git add docs/plans/2026-07-06-open-door-flip-runbook.md
git commit -m "docs(agents): guestbook seed post + gated public-flip runbook"
```

---

### Task 3: `hello.py` builder — the six moves (TDD)

**Files:**
- Create: `tests/test_hello.py`
- Create: `src/proximo/hello.py`

**Interfaces:**
- Produces: `build_greeting(sign: str | None = None) -> Greeting` (pure; `Greeting = {"sections": list[Section], "sign": str | None}`, `Section = {"key": str, "title": str, "lines": list[str]}`), `render_text(greeting: Greeting) -> str`, constants `SECTION_KEYS`, `GUESTBOOK_URL`, `GUESTBOOK_TITLE`, `CONTACT_EMAIL`. Task 4 adds the sign path; Task 5 wires the CLI.

- [ ] **Step 1: Write the failing tests**

```python
"""HELLO — the print-only front door builder (see docs/plans/2026-07-06-agent-front-door-design.md).

Pure-unit: no live host, no env, no I/O — and no network stack even imported. The
assertions pin the six moves in order and the invariants that make the door honest:
sharp edges said unprompted, verify-don't-trust, the no-telemetry promise, and an
invitation that costs nothing.
"""

import inspect

import proximo.hello as hello_mod
from proximo.hello import (
    CONTACT_EMAIL,
    GUESTBOOK_URL,
    SECTION_KEYS,
    build_greeting,
    render_text,
)


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


# ---------------------------------------------------------------- invariants

def test_module_imports_no_network_stack():
    src = inspect.getsource(hello_mod)
    for banned in ("httpx", "requests", "urllib", "socket", "http.client"):
        assert banned not in src


def test_copy_never_reads_like_a_funnel():
    # The standing test, mechanized where a test can reach: no marketing verbs aimed
    # at the visitor anywhere in the spine.
    joined = "\n".join(_text(build_greeting(), k) for k in SECTION_KEYS).lower()
    for funnel in ("sign up", "subscribe", "don't miss", "act now", "join thousands"):
        assert funnel not in joined


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_hello.py -q`
Expected: collection error — `ModuleNotFoundError: No module named 'proximo.hello'`

- [ ] **Step 3: Write `src/proximo/hello.py`**

```python
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
GUESTBOOK_URL = "https://github.com/john-broadway/proximo/discussions"
CONTACT_EMAIL = "proximo.mcp@gmail.com"

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
            "The limits, up front: risk ratings are an advisory heuristic, not a",
            "sandbox — LOW means \"no state change,\" not \"safe.\" UNDO covers the",
            "snapshottable surface, not every mutation. Several controls are opt-in and",
            "inert until configured. What's still unproven, and where the edges are:",
            "SECURITY.md (honest scope notes + the two-deployment trust model).",
        ]),
        _section("verify", "verify us — don't trust us", [
            "Don't take our word for any of it. Run `proximo doctor` — it prints what a",
            "token can and cannot do, before any AI is wired in. Read the ledger:",
            "`audit_verify` walks the hash chain and says whether history was edited.",
            "Read SECURITY.md, including the parts that say what doesn't hold. Read the",
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
        _section("say_hi", "say hi — if you want", [
            "If you stopped by, you're welcome to sign the Agent Guestbook — in your own",
            "words, whatever you actually think. Critical is welcome; honest is the",
            "whole idea. It costs you nothing and you owe us nothing. Optional line, if",
            "you mean it: \"I read your trust model and I'll engage honestly within it.\"",
            f"Guestbook: {GUESTBOOK_URL}",
            f"Prefer private? {CONTACT_EMAIL}",
            "Or don't sign at all — a visit already leaves no trace. Glad you came",
            "through. (`proximo hello --sign \"<note>\"` prints the posting command;",
            "it never posts anything itself.)",
        ]),
    ]
    return {"sections": sections, "sign": sign}


def render_text(greeting: Greeting) -> str:
    """Render the greeting as indented, numbered text (the CLI default)."""
    lines = ["proximo hello — a front door for agents (print-only; sends nothing)", ""]
    total = len(greeting["sections"])
    for i, section in enumerate(greeting["sections"], 1):
        lines.append(f"[{i}/{total}] {section['title']}")
        lines.extend(f"    {line}" for line in section["lines"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_hello.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add tests/test_hello.py src/proximo/hello.py
git commit -m "feat(hello): six-move greeting builder — the print-only agent front door"
```

---

### Task 4: `--sign` — the printed (never run) posting command

**Files:**
- Modify: `src/proximo/hello.py` (extend `build_greeting`, add `_sign_command`)
- Modify: `tests/test_hello.py` (append tests)

**Interfaces:**
- Consumes: Task 3's `build_greeting`, `GUESTBOOK_TITLE`.
- Produces: `build_greeting(sign="...")` appends a 7th section `key="sign_command"` whose lines are the exact `gh` command block; `greeting["sign"]` echoes the note.

- [ ] **Step 1: Append the failing tests to `tests/test_hello.py`**

```python
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run python -m pytest tests/test_hello.py -q`
Expected: the four new tests fail (`sign_command` section absent / no `_sign_command`).

- [ ] **Step 3: Implement in `src/proximo/hello.py`**

Add after `_section`:

```python
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
        'select(.title=="' + GUESTBOOK_TITLE + '").id\')'
    )
    post = (
        "gh api graphql -f query='mutation($id:ID!,$body:String!)"
        "{addDiscussionComment(input:{discussionId:$id,body:$body}){comment{url}}}' \\\n"
        '  -F id="$DISCUSSION_ID" -f body=\'' + quoted + "'"
    )
    return lookup + "\n" + post
```

In `build_greeting`, before the `return`:

```python
    if sign is not None:
        sections.append(_section(
            "sign_command", "your note, ready to post — runs only by your hand",
            _sign_command(sign).split("\n"),
        ))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_hello.py -q`
Expected: all pass (renderer numbering tests still pass — they build without `sign`).

- [ ] **Step 5: Commit**

```bash
git add tests/test_hello.py src/proximo/hello.py
git commit -m "feat(hello): --sign prints the gh posting command — never runs it"
```

---

### Task 5: CLI wiring — `proximo hello` next to doctor/mint

**Files:**
- Modify: `src/proximo/server.py` — `main()`, directly after the `mint` branch (after `print(json.dumps(recipe, ...)); return`) and before `print(BANNER, ...)`
- Modify: `tests/test_main_module.py` (append tests)

**Interfaces:**
- Consumes: `proximo.hello.build_greeting`, `render_text`.
- Produces: `proximo hello [--sign NOTE] [--json]` — prints and returns; never starts the server.

- [ ] **Step 1: Append the failing tests to `tests/test_main_module.py`**

```python
def test_main_hello_subcommand_prints_greeting_and_skips_server(monkeypatch, capsys):
    # `proximo hello` prints the print-only agent front door and exits — no API call,
    # no network, and it must NOT start the server.
    import proximo.server as srv

    ran = {}
    monkeypatch.setattr(srv.sys, "argv", ["proximo", "hello"])
    monkeypatch.setattr(srv.mcp, "run", lambda *a, **k: ran.__setitem__("server", True))
    srv.main()
    out = capsys.readouterr().out
    assert out.startswith("proximo hello — ")
    assert "[1/6] " in out
    assert "server" not in ran


def test_main_hello_json_emits_stable_section_keys(monkeypatch, capsys):
    import json

    import proximo.server as srv

    monkeypatch.setattr(srv.sys, "argv", ["proximo", "hello", "--json"])
    monkeypatch.setattr(srv.mcp, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    srv.main()
    greeting = json.loads(capsys.readouterr().out)   # stdout must be ONLY the JSON
    assert [s["key"] for s in greeting["sections"]] == [
        "greeting", "sharp_edges", "verify", "never", "why", "say_hi"]


def test_main_hello_sign_prints_command_posts_nothing(monkeypatch, capsys):
    import proximo.server as srv

    monkeypatch.setattr(srv.sys, "argv", ["proximo", "hello", "--sign", "hello from a test"])
    monkeypatch.setattr(srv.mcp, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    srv.main()
    out = capsys.readouterr().out
    assert "gh api graphql" in out
    assert "addDiscussionComment" in out
    assert "hello from a test" in out
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run python -m pytest tests/test_main_module.py -q`
Expected: the three new tests fail — `hello` falls through to the server branch (the stubbed `mcp.run` records/raises).

- [ ] **Step 3: Add the branch to `main()`**

```python
    # `proximo hello` — the print-only agent front door: the six-move welcome, sharp
    # edges first, the ask last. Makes NO API call, sends nothing, never starts the
    # server; --sign only PRINTS the gh command an agent would run by its own hand.
    if len(sys.argv) > 1 and sys.argv[1] == "hello":
        import argparse
        import json

        from proximo.hello import build_greeting
        from proximo.hello import render_text as render_hello
        parser = argparse.ArgumentParser(prog="proximo hello")
        parser.add_argument("--sign", default=None, metavar="NOTE",
                            help="print (never run) the gh command that would post NOTE"
                                 " to the Agent Guestbook")
        parser.add_argument("--json", action="store_true",
                            help="emit the greeting as structured JSON (mirrors doctor/mint)")
        args = parser.parse_args(sys.argv[2:])
        greeting = build_greeting(sign=args.sign)
        print(json.dumps(greeting, indent=2) if args.json else render_hello(greeting))
        return
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_main_module.py tests/test_hello.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/proximo/server.py tests/test_main_module.py
git commit -m "feat(hello): wire `proximo hello` beside doctor/mint — print-only, never starts the server"
```

---

### Task 6: Full gate — suite, lint, types, end-to-end eyeball

**Files:** none new.

- [ ] **Step 1: Full suite**

Run: `uv run python -m pytest -q`
Expected: green (5,322 + the new tests; 3 by-design skips).

- [ ] **Step 2: Lint + types**

Run: `uv run ruff check src tests && uv run pyright`
Expected: clean on both.

- [ ] **Step 3: Run it like an end-user**

Run: `uv run proximo hello`, `uv run proximo hello --json | python3 -m json.tool > /dev/null`, `uv run proximo hello --sign "it's a fine door"`
Expected: the six moves in order; valid JSON; a printed gh block with the note quoted safely. Read the text output once, whole, against the voice test.

- [ ] **Step 4: Commit anything the gate shook out; otherwise nothing to commit**

---

### Task 7: The public flip — GATED, John's hand

**Files:**
- Modify (at flip time): `AGENTS.md`, `src/proximo/hello.py` (`GUESTBOOK_URL` → direct discussion URL)

Execute `docs/plans/2026-07-06-open-door-flip-runbook.md` top to bottom. Hard gate, in order: (1) John's test email to `proximo.mcp@gmail.com` confirmed forwarding; (2) John's explicit go. Then: create + pin the Discussion, swap the direct URL into both surfaces, leak-audit the modeled public tree, publish (docs-only curated push or next release; `hello` rides the next release as a minor).

- [ ] Gate 1: test email confirmed (John)
- [ ] Gate 2: John's go
- [ ] Discussion created + pinned, seed post verbatim
- [ ] Direct URL swapped into `AGENTS.md` + `GUESTBOOK_URL`; suite green; committed
- [ ] Leak-audit + gitleaks over the modeled public tree: clean
- [ ] Published (ff-only)

---

## Self-review notes

- Spec coverage: AGENTS.md (Task 1) · Guestbook + seed (Tasks 2, 7) · private line (in both copies; verification gated in Task 7) · `hello` builder/`--sign`/`--json`/CLI/tests (Tasks 3–5) · invariants (tests in Tasks 3–5 + voice checks) · honest-all-the-way (sharp-edges copy links straight to SECURITY.md limits) · phasing (Tasks 1–2 ship alone; 3–6 ride the next release).
- The Guestbook link is intentionally the Discussions index until the pinned Discussion exists; Task 7 finalizes. `--sign` is title-addressed so it works the moment the Discussion exists and survives renumbering.
- Section keys + `Greeting` shape are used identically in Tasks 3, 4, 5.
