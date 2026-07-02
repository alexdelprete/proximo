"""Proximo README demo — the trust arc, recorded live. READ-ONLY by construction.

Runs four real Proximo tool calls against a real Proxmox host and narrates them for a
terminal recording: doctor (what can this token do), a guest read, a DESTRUCTIVE delete
asked WITHOUT confirm (returns the PLAN — blast radius, risk, no action), and
audit_verify (the tamper-evident receipt). Nothing is mutated: the delete is never
confirmed, and the recording token is read-scoped anyway (defense in depth).

Reproduce:  PROXIMO_* env pointed at your host (a read-only token is enough), then
    uv run python scripts/demo/demo.py --vmid <a-throwaway-ctid>
Point PROXIMO_AUDIT_LOG at a scratch path for a clean ledger in the final beat.
The published cast/SVG was recorded against a live PVE 9.2 host with internal
identifiers redacted (IP/hostname shapes only — outputs are otherwise verbatim).
"""
from __future__ import annotations

import argparse
import logging
import sys
import time

DIM = "\x1b[2m"
BOLD = "\x1b[1m"
CYAN = "\x1b[36m"
GREEN = "\x1b[32m"
YELLOW = "\x1b[33m"
RED = "\x1b[31m"
RESET = "\x1b[0m"


def say(text: str = "", pause: float = 0.05) -> None:
    print(text, flush=True)
    time.sleep(pause)


def type_out(text: str, per_char: float = 0.018, pause: float = 0.35) -> None:
    for ch in text:
        sys.stdout.write(ch)
        sys.stdout.flush()
        time.sleep(per_char)
    sys.stdout.write("\n")
    sys.stdout.flush()
    time.sleep(pause)


def call(label: str) -> None:
    type_out(f"{CYAN}▸ tool:{RESET} {BOLD}{label}{RESET}")


def kv(key: str, value: str, color: str = "") -> None:
    say(f"    {DIM}{key}:{RESET} {color}{value}{RESET}", 0.10)


def main() -> None:
    ap = argparse.ArgumentParser(description="Proximo trust-arc demo (read-only)")
    ap.add_argument("--vmid", required=True, help="a THROWAWAY guest id to plan (never executed) against")
    args = ap.parse_args()

    logging.getLogger("httpx").setLevel(logging.WARNING)  # keep API URLs off camera
    from proximo import server  # late import: env must be loaded by the wrapper/caller

    say(f"{BOLD}Proximo{RESET} — the Proxmox MCP you can hand the keys", 1.2)
    say(f"{DIM}recorded live · real PVE host · read-only token · nothing staged{RESET}", 1.6)
    say()

    call("pve_doctor")
    doc = server.pve_doctor()
    kv("reachable", str(doc.get("reachable")).lower(), GREEN)
    ver = doc.get("version", {})
    kv("proxmox", f"PVE {ver.get('version', '?')}")
    token = doc.get("token", {})
    can, cannot = token.get("can", []), token.get("cannot", [])
    kv("token CAN", f"{len(can)} capability — {can[0]['capability']}" if can else "0")
    kv("token CANNOT", f"{len(cannot)} capabilities (each gap names the exact privilege + role to grant)")
    say(f"    {DIM}least privilege, made visible — before you wire in an agent{RESET}", 1.8)
    say()

    call(f"pve_guest_status  vmid={args.vmid}")
    st = server.pve_guest_status(vmid=args.vmid, kind="lxc")
    kv("guest", f"lxc/{args.vmid}  name={st.get('name')}  status={st.get('status')}")
    say("", 1.2)

    say(f"{DIM}now ask for the scariest thing a tool can do:{RESET}", 0.8)
    call(f"pve_delete_guest  vmid={args.vmid}  confirm=false")
    plan = server.pve_delete_guest(vmid=args.vmid, kind="lxc", confirm=False)
    kv("status", str(plan.get("status")), YELLOW + BOLD)
    kv("risk", str(plan.get("risk")).upper(), RED + BOLD)
    for line in plan.get("blast_radius", [])[:1]:
        kv("blast_radius", line, RED)
    for item in plan.get("affected", [])[:2]:
        kv("affected", f"{item.get('kind')}: {item.get('effect')}")
    kv("to_proceed", str(plan.get("to_proceed")))
    say(f"    {DIM}a destroy without confirm returns a PLAN — blast radius named, nothing touched{RESET}", 2.2)
    say()

    call("audit_verify")
    ver2 = server.audit_verify()
    keyed = str(ver2.get("keyed")).lower()
    kv("ledger", f"ok={str(ver2.get('ok')).lower()}  entries={ver2.get('entries')}  keyed={keyed}", GREEN)
    kv("head", str(ver2.get("head", ""))[:40] + "…")
    say(f"    {DIM}every step above already landed in a hash-chained, tamper-evident ledger{RESET}", 2.0)
    say()

    say(f"{BOLD}Nothing was touched. Everything was recorded.{RESET}", 1.0)
    say(f"{DIM}pip install proximo-proxmox   ·   github.com/john-broadway/proximo{RESET}", 4.0)
    say("", 0.05)  # trailing event so the closing frame survives in the rendered cast


if __name__ == "__main__":
    main()
