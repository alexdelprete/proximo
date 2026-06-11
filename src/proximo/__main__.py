"""Entry point for ``python -m proximo`` — starts the MCP stdio server.

Mirrors the ``proximo`` console script (``proximo.server:main``); both are stdio,
on-demand, no daemon. Wire either into your MCP client.
"""
from proximo.server import main

if __name__ == "__main__":
    main()
