#!/usr/bin/env python3
"""Report Proximo's global install/download reach across every countable surface.

Turns the ad-hoc "what's our download count" question into one reproducible view:

    python scripts/reach.py            # human table
    python scripts/reach.py --json     # machine-readable

Surfaces:
  * PyPI   (proximo-proxmox) — pypistats recent counts (last day/week/month).
  * Docker Hub (jebroadway/proximo) — pull_count. GHCR exposes no pull count, so
    the release pipeline mirrors the image here (see .github/workflows/dockerhub-mirror.yml);
    until the first mirror lands this reads "not yet mirrored".
  * HuggingFace (john-broadway RYS models) — all-time + last-30d downloads.

Honesty notes baked into the output:
  * PyPI/Docker counts include CI, mirrors, and bots — treat as reach, not humans.
  * GHCR pull counts are unmeasurable at the source; Docker Hub is the proxy.

Stdlib only — no deps, runs under any python3.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

PYPI_PACKAGE = "proximo-proxmox"
DOCKERHUB_REPO = "jebroadway/proximo"
HF_AUTHOR = "john-broadway"

TIMEOUT = 15


def _get_json(url: str) -> dict | list | None:
    """GET a URL and parse JSON. Returns None on any failure (surface stays 'unavailable')."""
    if not url.startswith("https://"):  # only ever called with the fixed https constants above; enforce it
        return None
    req = urllib.request.Request(url, headers={"User-Agent": "proximo-reach/1.0"})  # noqa: S310 — https enforced above
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:  # noqa: S310 — https enforced above
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, TimeoutError):
        return None


def pypi_reach() -> dict:
    data = _get_json(f"https://pypistats.org/api/packages/{PYPI_PACKAGE}/recent")
    if not data or "data" not in data:
        return {"surface": "PyPI", "package": PYPI_PACKAGE, "available": False}
    d = data["data"]
    return {
        "surface": "PyPI",
        "package": PYPI_PACKAGE,
        "available": True,
        "last_day": d.get("last_day"),
        "last_week": d.get("last_week"),
        "last_month": d.get("last_month"),
    }


def dockerhub_reach() -> dict:
    data = _get_json(f"https://hub.docker.com/v2/repositories/{DOCKERHUB_REPO}/")
    if not data:
        # 404 until the first mirror runs — a distinct, honest state, not an error.
        return {"surface": "Docker Hub", "repo": DOCKERHUB_REPO, "available": False,
                "note": "not yet mirrored — run the dockerhub-mirror workflow"}
    return {
        "surface": "Docker Hub",
        "repo": DOCKERHUB_REPO,
        "available": True,
        "pull_count": data.get("pull_count"),
    }


def hf_reach() -> dict:
    url = (f"https://huggingface.co/api/models?author={HF_AUTHOR}"
           "&expand[]=downloadsAllTime&expand[]=downloads&limit=100")
    data = _get_json(url)
    if not isinstance(data, list):
        return {"surface": "HuggingFace", "author": HF_AUTHOR, "available": False}
    all_time = sum((m.get("downloadsAllTime") or 0) for m in data)
    last_30d = sum((m.get("downloads") or 0) for m in data)
    return {
        "surface": "HuggingFace",
        "author": HF_AUTHOR,
        "available": True,
        "repos": len(data),
        "all_time": all_time,
        "last_30d": last_30d,
    }


def _fmt(n: object) -> str:
    return f"{n:,}" if isinstance(n, int) else "—"


def render_table(surfaces: list[dict]) -> str:
    lines = ["", "Proximo — global reach", "=" * 48]
    for s in surfaces:
        if not s.get("available"):
            note = s.get("note", "unavailable")
            lines.append(f"{s['surface']:<14} {note}")
            continue
        if s["surface"] == "PyPI":
            lines.append(f"{'PyPI':<14} {_fmt(s['last_month'])}/mo  ·  "
                         f"{_fmt(s['last_week'])}/wk  ·  {_fmt(s['last_day'])}/day   ({s['package']})")
        elif s["surface"] == "Docker Hub":
            lines.append(f"{'Docker Hub':<14} {_fmt(s['pull_count'])} pulls (all-time)   ({s['repo']})")
        elif s["surface"] == "HuggingFace":
            lines.append(f"{'HuggingFace':<14} {_fmt(s['all_time'])} all-time  ·  "
                         f"{_fmt(s['last_30d'])}/30d   ({s['repos']} RYS repos)")
    lines.append("-" * 48)
    lines.append("Counts include CI / mirrors / bots — reach, not humans.")
    lines.append("GHCR pull counts are unmeasurable at source; Docker Hub is the proxy.")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Report Proximo's global download reach.")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = ap.parse_args()

    surfaces = [pypi_reach(), dockerhub_reach(), hf_reach()]

    if args.json:
        print(json.dumps({"surfaces": surfaces}, indent=2))
    else:
        print(render_table(surfaces))
    return 0


if __name__ == "__main__":
    sys.exit(main())
