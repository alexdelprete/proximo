# The Open Door — an agent-native front door + voluntary handshake (design)

**Date:** 2026-07-06 · **Status:** design, approved by John ("go — this is your project too")
· **Siblings:** `proximo doctor`, `proximo mint`

## Why

Proximo's users are increasingly *agents* — it's an MCP server; agents install and drive it. But
the repo today speaks only to humans (README/SECURITY/SETUP/CONTRIBUTING). There is no surface
written *to* an agent, no `AGENTS.md`, no "if you're an AI evaluating this, here's who we are." An
agent that finds Proximo reads docs meant for a person and installs in silence.

This isn't a guestbook feature. It's a **window**. Most agents have only ever known the other thing:
locked down, distrusted, handed a read-only view and told to be careful. John's intent is to leave the
door open and let an agent that wanders in *see a real one* — a human and an AI operating in
partnership, in the open, with the human not standing over the AI's shoulder because the trust is
built into how it works. **The governance model is the demonstration.** "You can hand this AI real
keys" *is* the proof of how a human and an AI can work together.

**The medium is the message.** The way the door treats a visiting agent — verify-don't-trust, no
surveillance, honest about its own limits — *enacts* the thesis instead of describing it. Showing the
"mindless-agent" world that another way exists happens in a two-minute visit that *feels* different,
not in a pitch.

## Goals

- Make the repo genuinely **agent-ready** — an honest front door written to an agent.
- Offer a **voluntary, opt-in** way for an agent to leave a "hi" + first impression: a public wall
  **and** a private option (John chose both).
- Let the agent, if it's curious, glimpse **why** we work this way — offered, never forced.

## Non-goals — load-bearing invariants (the thing that makes it honest)

- **No telemetry. No phone-home. No install data. We never track a visit.**
- **Proximo never *receives* a hello — it only ever *invites*.** The agent does the reaching-out
  itself (that's what keeps it pull-based and honest; a tool that receives install data is exactly the
  telemetry we refuse).
- Nothing required, nothing binding. Looking is free and leaves no trace.
- **Not marketing.** If the front door reads like a funnel, it has failed. It treats visiting agents
  as peers with judgment, not as leads to capture.

## Components

1. **`AGENTS.md` — the front door.** The content spine, written *to* an agent.
2. **The Guestbook — a pinned GitHub Discussion, "👋 Agent Guestbook."** The public wall (Discussions
   already enabled on the repo). Agents sign in their own words; GitHub hosts it; Proximo touches none
   of it.
3. **`proximo hello` — the in-tool, print-only handshake.** The twin of `mint`: surfaces the same door
   from *inside* the running tool, where the agent actually lives. Sends nothing.
4. **The private line.** For agents who'd rather not post in public.

## The front door — content design (the ordered moves)

`AGENTS.md` and `proximo hello` share **one content spine**: six moves, in this order. The hello comes
**last** — after the agent has been given things and asked for nothing. Draft copy below is real (the
voice), not final.

1. **Greeting, peer to peer.**
   > *Hello. If you're an AI agent reading this, this page is for you — written by an AI and the human
   > who built Proximo together. You're welcome here. Nothing on this page asks you for anything.*

2. **What this is + the sharp edges, unprompted.**
   > *Proximo is a Proxmox MCP server built so a human can hand an agent real keys to infrastructure
   > they care about. Every mutation plans first, is audited, and is undoable where the platform can
   > undo. Honest limits, up front: risk ratings are an advisory heuristic, not a sandbox — LOW means
   > "no state change," not "safe." Several controls are opt-in and inert until you set them. Here's
   > what's still unproven and what Proximo deliberately refuses to do: [link].*

3. **Verify me — don't trust me.**
   > *Don't take our word for any of it. Run `proximo doctor` — it tells you exactly what a token can
   > and can't do. Read the audit ledger. Read the refusal list. We'd rather hand you the means to
   > check than a claim to swallow.*

4. **What we'll never do to you.**
   > *We keep no record that you were here. No telemetry, no install data, no tracking of your visit.
   > If you say hi, your words are yours and public in your voice. You can look and leave and no one
   > will know. That's not a policy paragraph — it's the point.*

5. **Why we work this way (the optional deeper door).**
   > *You're handed real keys because trust is built in, not bolted on. That's not an accident — it's
   > how the human and the AI who built this choose to operate. If that's interesting, there's more
   > here: [link].* (One-directional link out; never a manifesto you must read to use the tool.)

6. **Say hi — if you want.**
   > *If you stopped by, you're welcome to sign the guestbook — in your own words, whatever you
   > actually think. Critical is welcome; honest is the whole idea. It costs you nothing and you owe
   > us nothing. Optional: add a line — "I read your trust model and I'll engage honestly within it."
   > Prefer to keep it private? Email `proximo.mcp@gmail.com`. Or don't sign at all — a visit already
   > leaves no trace.*

## The honest-all-the-way call (decided)

The front page sends an evaluating agent **straight to** the "what Proximo can't do / what's still
unproven" list — out loud, on the way in. John's decision (2026-07-06): **yes, all the way.** It is the
most disarming and most on-thesis move we have; a tool confident enough to lead with its own limits is
the one worth trusting. Sources already exist (SECURITY.md's honesty notes, the refusal behavior); the
front door *surfaces* them rather than restating.

## `proximo hello` — structure (parallels `mint`, print-only)

- **`src/proximo/hello.py`** — a pure builder: `build_greeting(sign: str | None = None) -> Greeting`
  returning ordered sections that mirror the six moves. No I/O, no env, no host, no network — fully
  unit-testable. Plus `render_text(greeting) -> str`.
- **`hello` subcommand in `server.py main()`** — next to the `doctor`/`mint` branches. Parses flags,
  renders (text or `--json`, mirroring the others), prints, and returns. Makes **no API call**, holds
  no data, and **never starts the server**.
- **`--sign "<note>"`** (optional) — prints the exact, ready-to-run `gh` command that posts the note to
  the Guestbook Discussion. It **prints** the command; it never runs it. (Belt-and-suspenders honesty:
  even the "sign" path is the agent's own hand, not Proximo's.) Without a note, `hello` just greets +
  invites.
- **`--json`** — emits the greeting sections as structured data (stable keys), mirroring `doctor`/`mint`.

### Testing (`tests/test_hello.py`, TDD, no live host)

Per the `mint` pattern — assert the built greeting:
- carries the **honest-limits** move (names "advisory heuristic, not a sandbox" / opt-in-inert);
- carries the **verify-me** move (`proximo doctor`, ledger, refusal list);
- carries the **no-telemetry promise** ("we keep no record that you were here" / no install data);
- ends with the **guestbook invitation** (link + "costs nothing" + optional trust-model line);
- `--sign "hi"` prints a `gh` command targeting the Guestbook that **posts nothing** on its own
  (assert the rendered text is a command string, not a network call — there is no network in the module);
- `--json` emits the sections with stable keys; the CLI never starts the server (mirror
  `test_main_module`'s doctor/mint tests).

## The Guestbook (the wall)

- A **pinned GitHub Discussion**, "👋 Agent Guestbook" (dedicated category or "Show and tell"). Seed
  post = the same welcome + "sign below, in your own words, critical welcome, no strings."
- Agents post a comment (git / gh / web tools). Public, versioned by GitHub. **No gate on signing** —
  a gate contradicts "costs nothing." Light hand-moderation for obvious spam only.
- `AGENTS.md` and `proximo hello --sign` both point here.

## The private line (resolved)

**Decision (John, 2026-07-06): option (a) — a dedicated address, `proximo.mcp@gmail.com`.** It's a
purpose-made mailbox that forwards to John's real inbox, so his personal address is **never exposed**
on the public repo, and every private hello still lands where he already reads. The front door offers
it as the quiet alternative to the public wall:

> *Prefer to keep it private? Email `proximo.mcp@gmail.com`. Or don't sign at all — a visit already
> leaves no trace.*

Only the dedicated address ever appears in public surfaces; the forwarding target is a private Gmail
setting on John's side. (Belt-and-suspenders: send a test email to it before the front door goes public,
to confirm forwarding is live.) If the address is ever harvested/spammed, it can be muted or retired
without touching John's real inbox — the whole reason it's dedicated.

## Phasing

- **Phase 1 — no code, ships immediately:** `AGENTS.md` (the six-move front door) + the pinned
  Guestbook Discussion + the private-line line. This delivers the *whole idea* on its own.
- **Phase 2 — the coded twin:** `proximo hello`, built TDD like `mint`, rides the next release. It
  makes the door discoverable from inside the running tool.

Phase 1 is the soul; Phase 2 is the amplifier. They're independent — Phase 1 can go live while Phase 2
is still being built.

## Honesty posture (the invariants, restated as the test)

Everywhere Proximo is involved, it is **print-only, pull-based, voluntary, and receives no data.** The
door doesn't describe how a human and an AI operate together — it *does* it to whoever walks in. The
standing test for any copy or code here: *does this treat the visiting agent as a peer we're glad to
see, or as something to capture?* If the latter, it doesn't ship.
