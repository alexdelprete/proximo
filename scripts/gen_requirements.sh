#!/usr/bin/env bash
# Regenerate the hash-pinned lockfiles in requirements/ — the files CI, the release
# workflows, and the Dockerfile install with `pip --require-hashes`.
#
#   runtime.txt  <- uv.lock (base deps; the image + the wheel-SBOM env)
#   dev.txt      <- uv.lock (base + dev extra; CI test env)
#   build.txt    <- build.in  (build backend: build/hatchling/editables), pinned
#                   consistently with dev.txt so the two files co-install
#   sbom.txt     <- sbom.in   (cyclonedx-bom), pinned consistently with runtime.txt
#
# Run after ANY dependency change (pyproject, uv lock). tests/test_requirements_lock.py
# fails when the exported pair drifts from uv.lock; release.sh regenerates + verifies all
# four in its gate.
set -euo pipefail
cd "$(dirname "$0")/.."

uv export --no-dev --no-emit-project --format requirements-txt -o requirements/runtime.txt
uv export --extra dev --no-emit-project --format requirements-txt -o requirements/dev.txt
uv pip compile --generate-hashes --universal -c requirements/dev.txt requirements/build.in -o requirements/build.txt
uv pip compile --generate-hashes --universal -c requirements/runtime.txt requirements/sbom.in -o requirements/sbom.txt
