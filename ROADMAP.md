# Proximo — Roadmap to the Complete, Provable Proxmox Control Plane

> Created 2026-06-08. The goal, stated at full size: **every operation Proxmox VE can perform,
> exposed as an MCP tool, with every mutating one PLANNED (dry-run first), UNDOABLE where the
> platform allows, and PROVED (tamper-evident ledger).** Not a focused subset. The whole surface,
> done right — the entire control plane safe to hand an AI. *(Aspirational — see the reality
> check below; most of the surface is not yet live-proven, and `proxxx` is a serious trust peer.)*

## Why total coverage is the design thesis, not just ambition

Most Proxmox MCP servers grow by adding tools over a flat, ungated surface. Proximo's design bet
is that breadth and trust compound rather than trade off:

- **For a flat tool, every new operation is new attack surface.** More tools means more ways an AI
  can damage a cluster with no preview, no undo, no record — risk grows with coverage.
- **For Proximo, every new operation is new _trust_ surface.** Because PLAN/UNDO/PROVE are the
  substrate every tool inherits, each operation added ships already dry-runnable, undoable, and
  provable — value grows with coverage.
- **The guarantee has to be substrate.** Adding a `create_vm` is easy; retrofitting plan-by-default,
  auto-snapshot undo, and a hash-chained ledger across 150 existing operations after the fact is not.

So the roadmap covers everything — including the planes most servers won't touch (network, SDN,
migration, HA, firewall, access/ACLs, PBS deep) — with the trust guarantee attached by construction.

## Where things stand (2026-06-10)

> **Reality check (updated 2026-06-10):** The governance/dangerous plane (ACL · users · roles ·
> realms · storage · SDN apply · network apply) is now **live-proven to execute** (create→read→delete
> against a real PVE 9.2 API on a nested test cluster; offline guest migration + HA-config on a nested
> 3-node test cluster). **Honest scope:** nested test cluster ≠ production scale. Two operations remain
> unproven: HA **fencing** (hardware watchdog) and **online** live-migration (shared storage). The audit
> ledger now supports opt-in HMAC-keyed mode; default stays unkeyed. ~**100 of 117 tools still have no
> live-fire beyond the proven operations** — a broad production smoke and publish (PyPI/GHCR) remain next.
> Full source-verified field comparison: `LANDSCAPE.md`.

✅ **Foundation built + live-proven** (the hard part, done first): PLAN · UNDO · PROVE · DIAGNOSE,
ledger verified against live PVE end-to-end. Every future tool inherits this.

✅ **A2A perimeter hardened:** fail-closed non-localhost bind; bearer auth + Host-header allowlist +
DNS-rebind defense. A2A stays opt-in; localhost-default dev behavior unchanged.

✅ **Governance/dangerous plane — live-proven to execute** (2026-06-10): ACL/role/group/user/realm
create+read+delete, storage, SDN apply, network apply executed against a real PVE 9.2 API on a nested
test cluster; offline migration + HA-config on a nested 3-node test cluster. PROVE ledger verified.
Realm create fixed (LDAP/AD/OpenID options dict). **Remaining unproven: HA fencing (hardware watchdog),
online live-migration (shared storage), production scale.**

✅ **Build order phases 1–7 BUILT** (117 MCP tools, 1960 tests green, ruff clean; not yet published):
- 1 provisioning+restore · 2 config mutation — **live-proven** (mutate cycle fired on real PVE).
- 4 cluster/HA/migration · 5 network/SDN/firewall · 6 access/ACL/realms — built+redteamed;
  **governance plane now live-proven** (see above); firewall/SDN network-apply mutate also proven.
- 7 observability + task/pool control + PBS-native deep — built+redteamed 2026-06-08; the READ
  half live-verified, including a live-found `node_journal`→`list[str]` shape fix;
  mutations not yet live-fired.
- Partial: 3 (storage create/remove, ISO/template upload) and 6 (groups/role-CRUD/TFA/
  user-CRUD) — the only remaining ☐ coverage.

## What's genuinely next

1. **Publish — PyPI/GHCR** (maintainer's call): CI, install commands, public tag.
2. **Prove at production scale:** broad live smoke across the full 117-tool surface on a real
   production-grade cluster with a properly-scoped token.
3. **HA fencing (hardware watchdog):** the fencing path cannot be proven without real watchdog
   hardware — unproven by design until the right hardware is available.
4. **Online live-migration (shared storage):** offline migration is proven; online migration
   requires shared storage backing — unproven until that environment is available.

## The complete surface — mapped, with status

`✅ done · ◐ partial · ☐ to build`. Trust column = which pillars each group must wear.

### A. Nodes & observability
- ◐ node status · ☐ node services (start/stop/restart) · ☐ RRD metrics / time-series ·
  ☐ journal / syslog / netstat / dns reads · ☐ subscription/cert reads. *(PLAN+PROVE on the mutating few.)*

### B. Guests — QEMU VMs & LXC (the core)
- ✅ list · ✅ status · ✅ power (start/stop/reboot/shutdown) · ✅ snapshot list/create/rollback/delete
- ☐ **create · clone · delete** (provisioning — the dangerous ops; PLAN+UNDO+PROVE, destroy is HIGH)
- ☐ **config edit** (cpu/mem/disk/net/options) with config-snapshot UNDO
- ☐ **resize disk · move disk** · ☐ template convert · ☐ cloud-init config
- ✅ container exec (ssh→pct, opt-in) · ◐ VM agent exec · ☐ VNC/console broker

### C. Backup & restore (most on-thesis — UNDO's true home)
- ☐ **vzdump backup** (create, list, delete, prune) · ☐ **restore** (the literal UNDO pillar, missing today)
- ☐ PBS integration: backup, verify, prune, garbage-collect, schedules, restore-from-PBS
  *(Restore is the highest-value gap: it is what UNDO means at the cluster level.)*

### D. Storage
- ◐ storage list · ☐ storage create/remove · ☐ content list · ☐ ISO + CT-template upload/download/delete
- ☐ volume management · ☐ vzdump backup catalog. *(PLAN+PROVE; deletes are HIGH.)*

### E. Migration, cluster & HA (high-stakes → trust shines brightest)
- ✅ offline **migrate** · ✅ cluster status/resources · ✅ HA resources (add/remove) ·
  ✅ **HA rules CRUD** (create/update/delete — node-affinity + resource-affinity) ·
  ☐ replication jobs · ☐ cluster options. *(PLAN with real blast-radius; PROVE every move.)*
  *(**HA rules LIVE-PROVEN** on PVE 9.2 (2026-06-14): full chain create-VM → HA-manage → rule
  create/read/update/delete → teardown, all green, ledger verified, zero residue. HA *groups*
  CRUD deliberately NOT built — groups 500 at runtime on PVE 9 (migrated to rules). Live-surfaced
  fix: HA-rule PUT needs the `type` discriminator → `ha_rule_update` auto-fetches it. Smoke:
  `scripts/live-smoke/harules-smoke.py`.)*

### F. Network & SDN (rarely covered by MCP servers)
- ◐ bridges / bonds / VLANs (list, create, update, **apply**) · ✅ **SDN zones / vnets / subnets CRUD** ·
  ☐ pending-vs-applied diff. *(Network changes are connectivity-lockout risk → PLAN is mandatory,
  apply is a guarded two-step. This is where "preview before you commit" saves a cluster.)*
  *(**SDN zone/vnet/subnet CRUD LIVE-PROVEN** on PVE 9.2 (2026-06-14): full simple-zone → vnet →
  subnet create→read→update→delete chain, ledger verified, zero residue, and **`sdn_apply` NEVER
  called** — proving pending objects stage and revert with no live-network effect. The PVE-derived
  subnet id (`zone-cidr`, e.g. `psmkz1-10.99.99.0-24`) confirmed live. Smoke:
  `scripts/live-smoke/sdn-smoke.py`.)*

### G. Firewall (cluster / node / guest) — ✅ TOTAL CRUD, LIVE-PROVEN (2026-06-14)
- ✅ rules CRUD · ✅ security groups (create/delete) · ✅ aliases (list/create/update/delete) ·
  ✅ IP sets (create/delete + CIDR-entry add/remove) · ✅ options (set_enabled + general options_set).
  *(Every change PLANNED + PROVED — firewall edits are exactly where silent mistakes hurt.)*
  *(Aliases/ipsets/security-groups/options-set added 2026-06-14: API-shape grounded against the live
  PVE 9.2 schema before implementation, built test-first, redteam-hardened. UNDO honestly absent —
  firewall config is config-file state, not a guest snapshot.)*
  *(**LIVE-PROVEN** on a nested PVE 9.2 test node: create→read→delete of alias / ip-set
  (+entry) / security-group objects all 200 OK, options read + options_set PLAN (risk=high), audit
  ledger verified, zero residue. Smoke: `scripts/live-smoke/fwobjects-smoke.{sh,py}`.)*

### H. Access, ACLs & governance (Proximo eats its own dogfood)
- ✅ users / groups / roles · ✅ **ACL grant/revoke** · ✅ API tokens (create/revoke) · ✅ realms · ✅ **TFA get/delete**
  *(TFA get/delete added 2026-06-14. Reads LIVE-PROVEN on PVE 9.2. **Live-verified caveat:** PVE
  forbids API *tokens* from mutating TFA — `tfa_delete` returns `403 need proper ticket` under token
  auth (PVE requires a ticket-based session); the tool is shape-correct + reaches the API. Enrollment
  is OUT (interactive challenge). Smoke: `scripts/live-smoke/tfa-smoke.py`.)*
- **Design note:** Proxmox ACL inheritance has a sharp edge — a grant on a deeper path *replaces*
  inherited grants rather than adding to them, which can silently shadow a token's access. An access
  tool that **PLANs an ACL change — showing what it shadows, what it widens, who it affects — and
  PROVEs it to the ledger** makes Proxmox permissions safe and auditable; the same plane can surface
  over-broad grants (e.g. a forgotten full-admin token) as first-class diagnostics.

### I. Pools, tasks & the ledger
- ☐ resource pools CRUD · ◐ task status → ☐ task list/log/stop/cancel/retry · ✅ ledger verify (PROVE)

## Build order (most-dangerous-first = most-differentiated-first, building toward TOTAL)

1. ✅ **Provisioning + Restore** — create/clone/delete (B) + backup/restore (C). LIVE-PROVEN.
2. ✅ **Config mutation** — guest config edits + resize/move + cloud-init (B). LIVE-PROVEN.
3. ◐ **Storage + ISO/templates** (D) — content/status/download/delete done; create/remove + upload TODO.
4. ✅ **Migration + cluster + HA** (E) — built+redteamed; **HA rules CRUD added 2026-06-14,
   LIVE-PROVEN on PVE 9.2** (full create→delete chain, ledger verified). HA groups CRUD N/A
   (runtime-500 on PVE 9). Replication jobs + cluster options remain future.
5. ◐ **Network + SDN + Firewall** (F, G) — network-apply + firewall-rules built+redteamed (mocked);
   **Firewall reached TOTAL CRUD 2026-06-14, LIVE-PROVEN on PVE 9.2** (aliases/ipsets/security-groups/
   options-set, test-first + redteam-hardened, create→read→delete proven against the live node, ledger
   verified). **SDN object CRUD (zones/vnets/subnets) added 2026-06-14, LIVE-PROVEN** (pending-only,
   no apply). Bridge/bond/VLAN host-net + pending-vs-applied diff remain future.
6. ◐ **Access / ACL / token governance** (H) — ACL/users/roles/tokens reads + acl/token mutate done;
   groups/role-CRUD/realms/TFA/user-CRUD TODO.
7. ✅ **Observability + PBS deep + task control** (A, C-PBS, I) — built+redteamed 2026-06-08;
   reads live-verified; mutations not yet live-fired.

Every phase follows the same discipline: built test-first → lint → independent adversarial review →
each tool wears the trust layer by construction → live-smoke on a throwaway target before "done."

## The one-line pitch when it's done

**"Every operation Proxmox can do — and every dangerous one previewed, reversible, and proven.
The complete control plane, safe to hand an AI."**
