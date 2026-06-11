# Proximo — self-contained, sovereign, on-demand.
# The MCP client launches it per session: `docker run -i --rm ... proximo` (stdio).
FROM python:3.13-slim

# openssh-client powers the in-container exec edge (ssh -> pct). Everything else is bundled by pip,
# so the image is self-contained and the host stays untouched.
RUN apt-get update \
 && apt-get install -y --no-install-recommends openssh-client \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir .

# MCP stdio server — no daemon, no open port. Launched on demand by the client.
ENTRYPOINT ["proximo"]
