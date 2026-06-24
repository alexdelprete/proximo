# Proximo — Setup (start here)

This guide gets you from nothing to a working, **safe** Proximo install. No prior experience assumed.
If you can log into your Proxmox web page, you can do this.

Proximo lets an AI assistant operate your Proxmox cluster. The reason it's safe to point at a box you
care about is **one idea**, so read this part first:

> **You create a Proxmox token. Proxmox itself enforces what that token can do. Proximo can never do
> more than the token allows — no matter what Proximo's code does, and no matter what the AI tries.**
>
> So you start with a **read-only** token: the AI can *look* at everything and *change* nothing —
> enforced by Proxmox, not by us. When you're ready, you grant write access on exactly the guests you
> choose, and nowhere else. The keys never leave your hand.

That's defense in depth, in the right order:

- **The floor — your token's permissions.** Enforced by Proxmox, held by you, impossible for Proximo to exceed.
- **On top — Proximo's safety net.** Every dangerous op is **planned** (dry-run + blast radius first),
  **undoable** (snapshots before it acts), and **proven** (a tamper-evident log of every move).

> 🔒 **Do every step below in YOUR OWN terminal / browser. Never paste your token secret into an AI chat.**

---

## Before you start

- A **Proxmox VE** server, and an admin login to it (you need admin *once*, to create the token).
- A machine with **Python 3.12+** (your laptop, a VM — anywhere; it talks to Proxmox over the network).
- *(Later, Step 5)* an MCP client — e.g. Claude Desktop or Claude Code.

---

## Step 1 — Install Proximo

```bash
pip install proximo-proxmox
```

(`pipx install proximo-proxmox` or `uvx proximo-proxmox` work too.) Confirm it landed:

```bash
pip show proximo-proxmox
```

---

## Step 2 — Create a least-privilege token in Proxmox  ← the important step

A **token** is an API key with its own permissions, separate from your password, and revocable any time.
We'll make a **read-only** one first. Pick the GUI *or* the CLI — they do the same thing.

### Option A — Proxmox web UI (click by click)

1. Log into the Proxmox web page as an admin.
2. **Datacenter → Permissions → Users → Add** → create user `proximo` in realm **`pve`** (Proxmox VE
   authentication server). A password is required by the form but you'll never use it — the token is separate.
3. **Datacenter → Permissions → API Tokens → Add** → User `proximo@pve`, Token ID `readonly`, leave
   **Privilege Separation CHECKED**. Click Add, then **copy the Secret now** — it's shown only once.
4. **Datacenter → Permissions → Add → API Token Permission** → Path `/`, API Token
   `proximo@pve!readonly`, Role **`PVEAuditor`**, Propagate checked. This grants **read-only across
   everything**.

### Option B — command line (on the Proxmox host)

```bash
pveum user add proximo@pve --comment "Proximo MCP (least-privilege)"
pveum user token add proximo@pve readonly --privsep 1
#   ^ copy the printed  value=<secret>  NOW — it is shown only once
pveum acl modify / --tokens 'proximo@pve!readonly' --roles PVEAuditor
```

`PVEAuditor` = look but never touch. (`--privsep 1` means the token's powers are exactly what *you*
grant to the token — it does not inherit your admin rights.)

### Save the token to a file

Proximo reads the token from a file whose **entire contents** are `USER@REALM!TOKENID=SECRET` (no
trailing newline):

```bash
mkdir -p ~/.config/proximo
printf '%s' 'proximo@pve!readonly=PASTE-THE-SECRET-HERE' > ~/.config/proximo/pve-token
chmod 600 ~/.config/proximo/pve-token
```

---

## Step 3 — Point Proximo at your server

Create `~/.config/proximo/proximo.env`:

```bash
PROXIMO_API_BASE_URL=https://YOUR-PVE-HOST:8006/api2/json   # your Proxmox address, port 8006
PROXIMO_NODE=YOUR-NODE-NAME                                 # the node name shown in the web UI
PROXIMO_TOKEN_PATH=/home/you/.config/proximo/pve-token      # the file from Step 2
PROXIMO_VERIFY_TLS=true
# If your Proxmox uses a self-signed certificate, DON'T disable TLS — point at its CA instead:
# PROXIMO_CA_BUNDLE=/home/you/.config/proximo/pve-ca.pem
```

(Container exec is **off** by default — leave `PROXIMO_ENABLE_EXEC` unset. It grants root on the host,
so it's strictly opt-in. You don't need it for normal use.)

---

## Step 4 — Verify YOUR boundary, before any AI sees it

This is the safety check. Load the config and run the built-in preflight:

```bash
set -a; . ~/.config/proximo/proximo.env; set +a
proximo doctor
```

You'll get JSON. Look for:

- `"reachable": true` — Proximo can talk to your Proxmox.
- `"token": { "can": [...], "cannot": [...] }` — **this is your safety boundary, in writing.**

With the read-only token, `can` lists only read/inspect, and **everything that changes state is in
`cannot`.** That is the guarantee, confirmed by Proxmox itself: no matter what the AI asks for, the
write simply won't be permitted. (If something's missing later, `cannot` even prints the exact `pveum`
command to grant it.)

If `reachable` is false or you see a TLS error, jump to **Troubleshooting** below.

---

## Step 5 — Wire Proximo into your AI client

Example — Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "proximo": {
      "command": "proximo",
      "env": {
        "PROXIMO_API_BASE_URL": "https://YOUR-PVE-HOST:8006/api2/json",
        "PROXIMO_NODE": "YOUR-NODE-NAME",
        "PROXIMO_TOKEN_PATH": "/home/you/.config/proximo/pve-token",
        "PROXIMO_VERIFY_TLS": "true"
      }
    }
  }
}
```

Restart the client, then ask it: **"run pve_doctor."** You'll see the same boundary you verified in
Step 4 — now the AI can answer questions about your cluster (what's running, is it healthy, is it
backed up) and **change nothing**, because your token says so.

---

## Step 6 — (Optional) Grant scoped write, when you're ready

Say you want the AI to be able to snapshot or restart **one** VM (id `100`) — and nothing else:

```bash
pveum acl modify /vms/100 --tokens 'proximo@pve!readonly' --roles PVEVMAdmin
```

Run `proximo doctor` again — power/snapshot/rollback now appear, **scoped to `/vms/100`**. Everything
Proximo does to that VM is planned, undoable, and logged; everything else stays read-only because the
token still says so. Grant only what you mean to, only where you mean it.

*(The token is named `readonly` — that's just a label. Its real power is whatever roles you grant it.)*

---

## Pull the keys anytime

Revoke instantly in the GUI (**Datacenter → Permissions → API Tokens → Remove**) or:

```bash
pveum user token remove proximo@pve readonly
```

The moment the token is gone, Proximo can do nothing at all.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| **TLS / certificate error** | Your Proxmox uses a self-signed cert. Point `PROXIMO_CA_BUNDLE` at the cluster CA — don't disable verification. |
| **401 Unauthorized** | Token secret wrong, or the file isn't exactly `user@realm!tokenid=secret` (no trailing newline). |
| **403 / a capability is in `cannot`** | The token lacks that privilege. Run `proximo doctor` — it prints the exact `pveum` command to grant it. If a grant doesn't take on a privsep token, some setups also want it on the user: `pveum acl modify <path> --users proximo@pve --roles <ROLE>`. |
| **Connection refused / timeout** | Wrong host or port (the Proxmox API is `:8006`), or a firewall in the way. |
| **`ct_exec` refused** | Exec is off by default (grants host root). It's opt-in via `PROXIMO_ENABLE_EXEC=1` + a CTID allowlist — only if you truly need it. |

---

Stuck? `proximo doctor` is the source of truth for what your token can and cannot do — start there.
