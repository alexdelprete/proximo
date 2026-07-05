#!/usr/bin/env python3
"""Regenerate lhm.plugin.json — the LobeHub Marketplace manifest — from the live server.

LobeHub scores a listing partly on declared capabilities (a non-empty `tools`
array sets the "tools" capability and satisfies the "Includes At Least One Skill"
required score item). Their crawler extracts tools by cold-starting the server and
calling `tools/list`; if that extraction ever misses, the listing drops to grade F.
Publishing an owner-declared `tools` array is authoritative and a re-crawl never
overwrites it, so we ship the real surface in the manifest.

This script cold-starts `proximo` over stdio with NO PROXIMO_* env (exactly the
crawler's view), reads the full tool list, and writes it into lhm.plugin.json with
the version single-sourced from pyproject.toml. Run at release time, then
`lhm plugin publish --dir .`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "lhm.plugin.json"

# Static listing fields. identifier is assigned by the marketplace at first
# listing — never invent it; keep name/description in sync with the README lead.
BASE = {
    "identifier": "john-broadway-proximo",
    "name": "Proximo",
    "description": (
        "The Proxmox MCP you can hand the keys — VE + Backup Server + Mail Gateway "
        "+ Datacenter Manager on one clean surface: every dangerous op planned, "
        "undoable, and audited."
    ),
}


def pyproject_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    return data["project"]["version"]


def list_capabilities(timeout: float = 90.0) -> dict[str, list[dict]]:
    """Cold-start proximo and return its tools + prompts — the crawler's-eye view.

    One stdio session, both `tools/list` and `prompts/list`, so the manifest
    declares every capability the server actually exposes on a cold start.
    """
    import selectors

    env = {k: v for k, v in os.environ.items() if not k.startswith("PROXIMO")}
    proc = subprocess.Popen(
        ["uv", "run", "proximo"],  # noqa: S603, S607  # dev/release helper; fixed argv, uv on PATH
        cwd=ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )

    def send(obj: dict) -> None:
        assert proc.stdin  # noqa: S101  # Popen(PIPE) guarantees these streams; assert documents the invariant
        proc.stdin.write((json.dumps(obj) + "\n").encode())
        proc.stdin.flush()

    # id 2 -> tools/list, id 3 -> prompts/list
    want = {2: "tools", 3: "prompts"}
    got: dict[str, list[dict]] = {}
    try:
        send({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05", "capabilities": {},
                "clientInfo": {"name": "gen-lobehub-manifest", "version": "1"},
            },
        })
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        send({"jsonrpc": "2.0", "id": 3, "method": "prompts/list", "params": {}})

        assert proc.stdout  # noqa: S101  # Popen(PIPE) guarantees this stream; assert documents the invariant
        sel = selectors.DefaultSelector()
        sel.register(proc.stdout, selectors.EVENT_READ)
        while len(got) < len(want):
            if not sel.select(timeout=timeout):
                break
            line = proc.stdout.readline()
            if not line:
                break
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = want.get(msg.get("id"))
            if key is not None:
                got[key] = msg.get("result", {}).get(key, [])
        if "tools" not in got:
            raise SystemExit(
                "no tools/list response; stderr tail:\n"
                + proc.stderr.read().decode(errors="replace")[-2000:]
            )
        return got
    finally:
        proc.kill()


def main() -> int:
    caps = list_capabilities()
    tools, prompts = caps.get("tools", []), caps.get("prompts", [])
    if not tools:
        raise SystemExit("refusing to write an empty tools array")
    manifest = {
        **BASE,
        "version": pyproject_version(),
        "tools": [
            {"name": t["name"], "description": t.get("description", ""),
             "inputSchema": t["inputSchema"]}
            for t in tools
        ],
    }
    if prompts:
        manifest["prompts"] = [
            {"name": p["name"], "description": p.get("description", ""),
             "arguments": p.get("arguments", [])}
            for p in prompts
        ]
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(
        f"wrote {MANIFEST.relative_to(ROOT)} — {len(tools)} tools, "
        f"{len(prompts)} prompts, v{manifest['version']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
