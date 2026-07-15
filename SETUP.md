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
  **proven** (a tamper-evident log of every move), and **undoable where the platform can snapshot**
  (it snapshots before it acts — guest/exec ops; firewall/SDN/ACL/token ops have no snapshot to revert to).

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

> Shortcut: `proximo mint` prints this whole step (and the next three) as an exact,
> copy-pasteable runbook for your product — `--product pve|pbs|pmg|pdm`, read-only by
> default, `--write` for the scoped write grant.

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
   everything** — to the token.
5. **Datacenter → Permissions → Add → User Permission** → Path `/`, User `proximo@pve`, Role
   **`PVEAuditor`**, Propagate checked. **Required, not optional:** a `--privsep`-checked token's
   effective permissions are the *intersection* of the user's grants and the token's grants — the
   user you just created has no ACL of its own, so without this step the intersection is empty and
   the token can do nothing.

### Option B — command line (on the Proxmox host)

```bash
pveum user add proximo@pve --comment "Proximo MCP (least-privilege)"
pveum user token add proximo@pve readonly --privsep 1
#   ^ copy the printed  value=<secret>  NOW — it is shown only once
pveum acl modify / --tokens 'proximo@pve!readonly' --roles PVEAuditor
# A privsep token's effective permissions are the INTERSECTION of the user's ACL and the
# token's ACL — the freshly-created user above has no ACL of its own, so it needs the role too:
pveum acl modify / --users 'proximo@pve' --roles PVEAuditor
```

`PVEAuditor` = look but never touch. (`--privsep 1` means a token's effective permissions are the
**intersection** of the user's ACL and the token's ACL, not the token's ACL alone — grant the role
to *both* the token and the user, and the token never inherits your admin rights either way.)

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
# same intersection rule as Step 2 — the privsep token needs the user's ACL to match, scoped
# to this same path, or the write grant to the token alone is a no-op:
pveum acl modify /vms/100 --users 'proximo@pve' --roles PVEVMAdmin
```

Run `proximo doctor` again — power/snapshot/rollback now appear, **scoped to `/vms/100`**. Everything
Proximo does to that VM is planned, undoable, and logged; everything else stays read-only because the
token still says so. Grant only what you mean to, only where you mean it.

*(The token is named `readonly` — that's just a label. Its real power is whatever roles you grant it.)*

---

## Remote / multi-client (optional)

Steps 1–5 run Proximo **beside your client**: the client spawns it, it talks to Proxmox, and nothing
listens on the network. That's the default on purpose — daemonless, no open port, nothing exposed.

If you want *one* Proximo that several machines or clients reach over the network, start from what
your client speaks:

| Your client speaks | Use | Extra | Bridge? |
|---|---|---|---|
| **REST / OpenAPI** — Open WebUI, dashboards, scripts, `curl` | `proximo-http` | `[http]` | No |
| **A2A** — agent-to-agent callers | `proximo-a2a` | `[a2a]` | No |
| **MCP** — Claude Desktop, Claude Code, Cursor | MCP is served over **stdio** only today | — | Yes — see below |

Both network faces serve the **full governed surface** through the same spine (PLAN · PROVE · UNDO —
and your token's ACL is still the floor). Both are opt-in, off unless you start them, and both carry
the same fail-closed perimeter: a non-localhost bind refuses to start without a bearer token, the
bearer is checked on every op, plus a Host/DNS-rebind allowlist and a CSRF guard.

### MCP over the network — a bridge, for now

The HTTP face speaks REST, not the MCP wire protocol, so an MCP client can't connect to it. Until a
native MCP-over-HTTP transport lands ([#25](https://github.com/john-broadway/proximo/issues/25)), a
remote MCP client needs a **stdio→HTTP bridge** in front of Proximo.

> ⚠️ **The bridge becomes your perimeter.** It wraps Proximo's *stdio* path, so the fail-closed
> perimeter above is **not** in the request path — whatever the bridge enforces is all there is. And
> bridges differ: the Python `sparfenyuk/mcp-proxy` has **no inbound auth at all** (its
> `API_ACCESS_TOKEN` is outbound-only, for when it acts as a client). Don't put an unauthenticated
> bridge in front of a hypervisor.
>
> Keep the token **read-only** (Step 2) until you've verified the perimeter yourself, and prefer
> reaching it over a VPN to exposing it publicly.

The recipe below uses [`punkpeye/mcp-proxy`](https://github.com/punkpeye/mcp-proxy) (npm), which
enforces an `X-API-Key` on inbound requests, serves streamable HTTP at `/mcp`, and passes the
container's environment to the Proximo child it spawns.

**`Dockerfile`** — Proximo plus the bridge, one image:

```dockerfile
FROM ghcr.io/john-broadway/proximo:0.22.0
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm \
 && npm install -g mcp-proxy@6.5.2 \
 && apt-get purge -y npm && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*
ENTRYPOINT ["mcp-proxy"]
```

**`proximo.env`** — as Step 3, but with the token path *inside* the container:

```bash
PROXIMO_API_BASE_URL=https://YOUR-PVE-HOST:8006/api2/json
PROXIMO_NODE=YOUR-NODE-NAME
PROXIMO_TOKEN_PATH=/etc/proximo/pve-token
PROXIMO_VERIFY_TLS=true
```

**`docker-compose.yml`** — keep `pve-token` (mode `600`, from Step 2) beside it:

```yaml
services:
  proximo:
    build: .
    container_name: proximo
    env_file: proximo.env
    environment:
      # The BRIDGE's inbound key — generate with: openssl rand -hex 32
      # Keep it here, not in proximo.env: that file is mounted into the container.
      - MCP_PROXY_API_KEY=YOUR_KEY
    volumes:
      - .:/etc/proximo:ro
    command: ["--host","0.0.0.0","--port","8096","--","proximo"]
    expose:
      - "8096"
    # attach to your reverse proxy's network; don't publish the port to the host
    networks: [proxy]
networks:
  proxy:
    external: true
```

`--` separates the bridge's own flags from the command it spawns (`proximo`). Put a reverse proxy in
front for TLS; the bridge answers an unauthenticated `GET /ping` for health checks.

**Verify the perimeter before you wire any client** — a request with no key must be refused:

```bash
docker compose exec proximo sh -lc \
  'node -e "fetch(\"http://127.0.0.1:8096/mcp\",{method:\"POST\"}).then(r=>console.log(r.status))"'
#   -> 401

docker compose exec proximo sh -lc \
  'node -e "fetch(\"http://127.0.0.1:8096/mcp\",{method:\"POST\",headers:{\"x-api-key\":\"YOUR_KEY\"}}).then(r=>console.log(r.status))"'
#   -> 400/406, i.e. the key was accepted and the request reached the MCP layer
```

**Claude Code** — connects natively, no shim:

```bash
claude mcp add --scope user --transport http proximo https://YOUR-HOST/mcp \
  --header "X-API-Key: YOUR_KEY"
```

`--scope user` matters: without it, `claude mcp add` defaults to *local* scope and the server is
registered only for the current directory.

**Claude Desktop** — needs a local shim to attach the header. Edit the config while Desktop is fully
closed (it rewrites that file from memory on exit, clobbering edits made while it runs):

```json
{
  "mcpServers": {
    "proximo": {
      "command": "uvx",
      "args": [
        "mcp-proxy",
        "--transport", "streamablehttp",
        "--headers", "X-API-Key", "YOUR_KEY",
        "https://YOUR-HOST/mcp"
      ]
    }
  }
}
```

Then ask either client **"run pve_doctor"** — the same boundary you verified in Step 4, now over the
network.

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
| **`Refusing to start: … group/other-accessible`** | Your token (or audit-key) file is readable by other users on the box. The message names the file — `chmod 600` it, exactly as in Step 2. Proximo won't run with an exposed secret. |
| **403 / a capability is in `cannot`** | The token lacks that privilege. Run `proximo doctor` — it prints the exact `pveum` command to grant it. For a `--privsep 1` token, effective permissions are the *intersection* of the user's ACL and the token's ACL: a freshly-created user has no ACL of its own, so the user-side grant is **always required**, not situational — `pveum acl modify <path> --users proximo@pve --roles <ROLE>`. |
| **Connection refused / timeout** | Wrong host or port (the Proxmox API is `:8006`), or a firewall in the way. |
| **`ct_exec` refused** | Exec is off by default (grants host root). It's opt-in via `PROXIMO_ENABLE_EXEC=1` + a CTID allowlist — only if you truly need it. |
| **A remote MCP client can't connect** | MCP is served over stdio only (see **Remote / multi-client**); the HTTP face speaks REST, not MCP. A networked MCP client needs a bridge — and the bridge's own auth is then your only perimeter. |

---

Stuck? `proximo doctor` is the source of truth for what your token can and cannot do — start there.
