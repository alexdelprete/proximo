# Proximo — self-contained, sovereign, on-demand.
# The MCP client launches it per session: `docker run -i --rm ... proximo` (stdio).
# Base pinned by digest for reproducible builds; the readable tag stays for humans.
# Dependabot's `docker` ecosystem bumps the digest weekly and Trivy re-scans the base
# on every push to main + weekly; the build layer also applies Debian's current security
# patches (apt-get upgrade below), so fixes land at build time, not only on the digest bump.
FROM python:3.13-slim@sha256:eb43ff125d8d58d7449dcba7d336c23bcac412f526d861db493b9994d8010280

# openssh-client powers the in-container exec edge (ssh -> pct). Everything else is bundled by pip,
# so the image is self-contained and the host stays untouched.
# `apt-get upgrade` applies Debian's current security patches at build time, so a newly-disclosed
# base CVE that already has a fix (e.g. liblzma5 CVE-2026-34743 -> 5.8.1-1+deb13u1) is remediated
# on the next build instead of waiting for the weekly Dependabot digest bump to carry it.
RUN apt-get update \
 && apt-get upgrade -y \
 && apt-get install -y --no-install-recommends openssh-client \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
# Allow-list copy: only what `pip install .` needs (hatchling builds the wheel from
# src/). The working tree is never copied wholesale, so a local `docker build` can't
# bake stray secrets (.env, keys, tokens) into the published image.
COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/
RUN pip install --no-cache-dir .

# MCP stdio server — no daemon, no open port. Launched on demand by the client.
ENTRYPOINT ["proximo"]
