# CLAUDE.md — proximo

Proximo is a **Proxmox MCP + A2A server**, published PUBLIC as `proximo-proxmox` (PyPI / GitHub / GHCR).
One clean tool surface over the Proxmox REST API (scoped token) plus opt-in in-container exec (`ssh` → `pct exec`), least-privilege and audited.

**This repo IS public.** No internal IPs, node names, org names, absolute `/root/...` paths, or tokens in tracked files. Never enter a secret via an AI agent's shell-passthrough prefix — it lands in the transcript (PyPI tokens have leaked this way). Pass secrets out-of-band, from your own terminal.

## Dev env — its OWN venv (NOT a shared workspace venv)

Proximo uses its own uv `.venv`. Always:

```
uv sync --extra dev                 # installs dev extras (pytest, ruff, pyright, a2a-sdk)
uv run python -m pytest -q          # full suite (2,500+ tests, 0 skipped) — the form every plan doc uses
uv run ruff check src tests
uv run pyright                      # type-checks src only (scoped in pyproject by design)
```

Run a single file: `uv run python -m pytest tests/test_blast.py -q`.

## Layout

- `src/proximo/server.py` — **all 145 `@mcp.tool()` definitions live here** (`mcp = FastMCP("proximo")`); the per-plane logic lives in sibling modules (`firewall.py`, `network.py`, `cluster_ops.py`, `access*.py`, `pbs.py`, `blast.py`, `storage*.py`, `planning.py`, `provisioning.py`, …).
- `src/proximo/a2a/` — the **optional** A2A (Agent2Agent) face; routes through the same trust core, no second mutate path.
- `tests/` — unit + structural-double tests, mirrored `test_<module>.py`.
- `scripts/live-smoke/` — live integration smokes; **deliberately outside `tests/`** so pytest never auto-collects them. They mutate a **real** PVE host against throwaway VMIDs/CTIDs and self-clean. Don't run them without a real host + scoped token.

## Trust spine (don't break these invariants)

Four pillars: **PLAN** (dry-run preview before any mutation — you can't mutate without a plan), **PROVE** (hash-chained tamper-evident audit ledger), **UNDO** (heterogeneous by plane: opt-in auto-snapshot for `ct_exec`/`ct_psql`, config-revert for guest config, `pve_rollback` for guests — fail-closed where present, but firewall/SDN/ACL/token planes aren't PVE-snapshottable so they have no rollback primitive; UNDO covers the snapshottable surface, not every mutation), **DIAGNOSE** (read-only evidence). Risk ratings are an **advisory heuristic, not a sandbox** — `LOW` = "no state change," not "safe." Keep that honesty note intact in any docs/output.

## Running the server

- MCP (stdio): the `proximo` command (= `python -m proximo` = `proximo.server:main`). Config via `PROXIMO_*` env (see `packaging/proximo.env.example`).
- **API-only by default.** In-container exec is opt-in (`PROXIMO_ENABLE_EXEC=1`) and grants near-root on the host — keep it loud and fail-closed (CTID allowlist).
- A2A: `pip install 'proximo-proxmox[a2a]'` then `proximo-a2a`; non-localhost binds refuse without a bearer token.

## Release / publish posture

- PUBLIC on PyPI (`proximo-proxmox` — bare `proximo` is reserved), GitHub, GHCR (signed multi-arch image). Command/import stay `proximo`.
- **PyPI publish is tokenless** via GitHub Actions OIDC Trusted Publishing (`.github/workflows/release-pypi.yml`), gated behind the `pypi` environment's required-reviewer rule — the publish job pauses for human approval. Cut a release: `scripts/release.sh X.Y.Z` (single-sources the version + runs the drift gate) → write the CHANGELOG entry → commit + tag `vX.Y.Z` → push → `gh release create` → approve the paused job. No API token in the release path (the old manual `uv publish` is retired).
- **Drift gate:** the `version-consistency` CI job + `scripts/version_tools.py` fail the build if `pyproject` / `__init__` / git tag / CHANGELOG disagree (`release-check` enforces the full set at release time).
- **GitHub `main` uses a curated/squashed history:** publish the tree from `scripts/release_leak_audit.py build-tree` (it strips internal-only paths like `.gitea/` and **refuses** if the public surface carries a leak shape) via `git commit-tree` parented on `github/main`, **fast-forward only, never force-push**. Full per-commit history lives on the internal gitea mirror. ⚠️ Remotes are inverted: `origin` = internal gitea, `github` = PUBLIC.
- **Honest semver:** pre-1.0 stays `0.x`. The version means maturity, bumped intentionally — never a per-deploy counter. Deploy identity = git SHA.
- **Before any public push: `scripts/release_leak_audit.py audit`** models the synthetic publish tree (which gitleaks / the pre-push hook never see) — no secrets / RFC1918 IPs / internal hostnames / `/root` paths / token shapes — then confirm the version, CHANGELOG, and any claimed counts are accurate. `release.sh` runs this audit in its gate.
