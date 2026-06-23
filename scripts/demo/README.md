# Proximo demo — "Hand the keys"

A real, recordable demo of the trust spine. The driver (`hand_the_keys.py`) calls Proximo's actual
code and prints its actual output — nothing is staged. That honesty *is* the pitch.

## Run it

```bash
# Local (self-contained — needs only `pip install proximo-proxmox`). You drive the tempo:
uv run python scripts/demo/hand_the_keys.py            # press Enter between beats
uv run python scripts/demo/hand_the_keys.py --auto 3   # hands-free, 3s/beat (asciinema)

# Full arc against a REAL host + a THROWAWAY guest (self-cleaning):
set -a; . /path/to/proximo.env; set +a
SMOKE_VMID=931 uv run python scripts/demo/hand_the_keys.py --live
```

## The story (≈90s)

The hook is the fear the market already votes on: people star the *read-only* Proxmox MCP because
they're scared to hand an AI agent the keys. The demo dissolves the trade-off — powerful **and** safe.

| Beat | On screen (local mode) | Caption / voiceover | ~secs |
|---|---|---|---|
| **Hook** | title card | "Would you hand an AI agent the keys to your cluster? Proximo is built so you can." | 0–8 |
| **1 · it's on the record** | three agent actions → `audit_verify ok=True, keyed=True` | "Every move an agent makes is hash-chained into a keyed ledger — by default." | 8–30 |
| **2 · you can't edit the past** | edit one entry → `ok=False, broken_at=2` | "Rewrite the record and the chain breaks. Tamper-evident, caught at the exact line." | 30–55 |
| **3 · you can't erase the tail** | truncate → forward walk fooled, `expected_head` catches it | "Delete the last entry and a naive check is fooled — but pin the head off-box and Proximo catches the wipe." | 55–82 |
| **Close** | `Strength and honor.` | "Plan it. Undo it. Prove it. Hand over the keys; keep the receipts." + repo URL | 82–90 |

For the **`--live`** cut, beat 1 becomes the showstopper: an agent asks to `pve_delete_guest(purge=True)`
and Proximo returns a **PLAN with the blast radius** and refuses to execute — *an agent cannot fumble
into an irreversible wipe.* Then a reversible change snapshots first (UNDO), then the PROVE receipt +
tamper. Use the live cut if you have a throwaway guest; the local cut works anywhere and is the safest
to record.

## Recording tips

- **asciinema** is ideal for a terminal demo: `asciinema rec proximo.cast` → run with `--auto 3` →
  Ctrl-D. Upload, or render to GIF/SVG (`agg`, `svg-term`) for embedding in the README / a post.
- Terminal ~100×30, a high-contrast theme, font bumped a couple sizes — the ANSI color is already
  tuned (dim = system, bold = caption, red/green = the verdicts).
- Keep the whole thing under ~90s. The tamper "ok=False" and the head-mismatch are the two moments
  that land — let them breathe (a beat of pause), cut the rest tight.

## Where to post (practitioner channels, not ad channels)

- r/homelab, r/Proxmox, r/selfhosted; the Proxmox community forum
- Show HN ("Show HN: Proximo — hand an AI agent your Proxmox cluster, keep the receipts")
- Lobsters; the MCP registries (PulseMCP, Glama, mcpmarket — where the competitors already are)
- Tie the writeup to the tailwind: OWASP MCP Top-10 **MCP08 (audit)** + "adoption outpaced governance."

Lead with the demo. This crowd watches before it reads.
