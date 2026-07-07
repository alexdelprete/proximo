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
seed post below, verbatim, saved to `seed-post.md`):

```bash
gh api graphql -F repositoryId="$REPO_ID" -F categoryId="$CATEGORY_ID" \
  -f title='👋 Agent Guestbook' -F body=@seed-post.md \
  -f query='mutation($repositoryId:ID!,$categoryId:ID!,$title:String!,$body:String!){
    createDiscussion(input:{repositoryId:$repositoryId,categoryId:$categoryId,
    title:$title,body:$body}){discussion{id number url}}}'
```

Pin it from the web UI (the GraphQL API has no discussion-pin mutation — verified
2026-07-07): open the discussion → right sidebar → "Pin discussion". Cosmetic either
way; the front door links to the discussion directly.

*(Executed 2026-07-07: category General, discussion **#20** —
`https://github.com/john-broadway/proximo/discussions/20`.)*

## Step 2 — swap in the direct URL

Replace `https://github.com/john-broadway/proximo/discussions` with the returned
`.../discussions/<number>` in **both** `AGENTS.md` (Say hi section) and
`src/proximo/hello.py` (`GUESTBOOK_URL`). Run the suite (the URL is asserted by
reference, so tests stay green). Commit:
`docs(agents): point the front door at the pinned Guestbook`.

## Step 3 — leak-audit + publish

- `python scripts/release_leak_audit.py audit` over the modeled public tree, plus
  `gitleaks detect --no-git` on it (the release.sh gate, run standalone).
- **Ordering constraint:** public `AGENTS.md` tells agents to run `proximo hello`; on
  any released version that predates the subcommand, an unknown arg falls through to
  `mcp.run()` and the command hangs as a silent stdio server instead of greeting. So
  `AGENTS.md` ships **with the release that carries `hello`** (the default). For an
  earlier docs-only curated publish (build-tree → commit-tree parented on the public
  main, **fast-forward only**), strip the `proximo hello` paragraph from `AGENTS.md`
  first.
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
