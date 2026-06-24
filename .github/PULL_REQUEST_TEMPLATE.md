<!-- Thanks for contributing to Proximo. Keep the trust spine at least as strong as you found it. -->

## What & why

<!-- What does this change, and why? Link any issue, e.g. Closes #123 -->

## Checks

- [ ] `uv run python -m pytest -q` is green (0 skipped)
- [ ] `uv run ruff check src tests` is clean
- [ ] `uv run pyright` is clean
- [ ] New behavior has a test; a bug fix has a test that fails before / passes after
- [ ] `CHANGELOG.md` updated under `## [Unreleased]` (or N/A — say why)

## Trust spine

- [ ] No mutation path bypasses **PLAN** (a preview is built + recorded before the change)
- [ ] No mutation path skips the **PROVE** ledger
- [ ] Safe defaults preserved: API-only by default, in-container exec still opt-in + loud
- [ ] No secret, token, internal hostname, or private IP in the diff

## Notes

<!-- Anything reviewers should know: breaking changes, follow-ups, things you're unsure about. -->
