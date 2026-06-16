# Spec — Blast-radius engine (firewall/network exposure class)

> Created 2026-06-15. Status: **pre-implementation, awaiting maintainer review.**
> Branch: `feat/firewall-network-blast-radius`. Author: brainstormed with the maintainer (advisor-reviewed).
> Prior op-classes (shipped to `main`): storage/disk (`docs/specs/2026-06-15-blast-radius-engine.md`),
> access/ACL (`docs/specs/2026-06-15-acl-blast-radius.md`).

## Motivation

Third and last of the named blast-radius op-classes. The headline: *"this rule exposes 22/tcp to
0.0.0.0/0"* and *"this apply drops the bridge holding the management IP."* Two distinct graphs, both
shipped in v1 (maintainer chose "both"):

- **A — firewall reach** (greenfield): `plan_firewall_rule_add` is *pure* and only **echoes** the rule
  fields (*"a misplaced DROP/REJECT can interrupt connectivity"*). It does **not** parse
  `(action, direction, source, dport, proto)` to compute what the rule actually permits/blocks, to
  whom, at what sensitivity. That semantic classification is the unbuilt, differentiated capability.
- **B — network/SDN apply lockout** (partly built): `plan_network_apply` already reads pending ifaces,
  is `RISK_HIGH` unconditional, and warns about lockout — but it does **not name** the specific
  interface a change touches or flag when that interface carries the management host.

## The load-bearing framing — PER-RULE REACH, not "effective exposure" (advisor-caught)

A firewall rule's *effect* is a property of the **whole ordered ruleset + default policy + enabled
state**, not the rule in isolation. A pure single-rule classifier therefore computes **per-rule
REACH**: *"what this rule permits/blocks IF it is the deciding match in an enforced, default-DROP
firewall."* It does **not** compute "is the cluster exposed."

Every `blast_radius` string and `affected` entry MUST be phrased as a property of **the rule** —
*"this rule permits 22/tcp from 0.0.0.0/0"* — and MUST NEVER assert *"your cluster is reachable from
the internet"* as fact. This is the same family of correction as storage's "cluster-wide or you
undercount" and ACL's "modifying bob doesn't change alice." It is a **framing constraint on the
wording**, not a scope decision. (It also makes deferring the firewall-enabled-state read honest: the
reach is stated *"assuming the firewall enforces this scope."*)

## v1 scope

- **A (in):** `compute_firewall_reach` wired into `plan_firewall_rule_add`, `plan_firewall_rule_remove`,
  `plan_firewall_rule_update`.
- **B (in):** mgmt-interface naming in `plan_network_apply`; a lighter touch on `plan_sdn_apply`.
- **Out (deferred):** resolving the full ordered-ruleset effective exposure (needs the whole ruleset +
  default policy); the firewall-enabled-state read (covered by the per-rule-reach disclaimer);
  resolving ipset/alias membership to concrete CIDRs (named, not resolved, in v1).

## Part A — pure firewall reach engine

`compute_firewall_reach(...)` in `blast.py` — PURE, no API. Inputs (all from the rule fields, plus the
management host from `cfg.api_base_url`, which is config not a network read):

```python
compute_firewall_reach(
    action: str,          # ACCEPT | DROP | REJECT
    direction: str,       # in | out
    source: str | None,
    dport: str | None,
    proto: str | None,
    scope_label: str,     # human scope ("cluster" / "node X" / "vm/100")
    enable: bool = True,  # enable=0 rule => staged-inert, not active
    mgmt_host: str | None = None,  # the host Proximo talks to (for self-lockout hints)
) -> FirewallReachResult
```

**Classification:**
- **Source breadth** (`_source_breadth`):
  - `None` / `""` / `0.0.0.0/0` / `::/0` → **"anywhere (the entire internet/WAN)"** — widest.
  - RFC1918 / loopback / link-local CIDR or host (`10/8`, `172.16/12`, `192.168/16`, `127/8`,
    `169.254/16`, `fc00::/7`, `fe80::/10`) → **"internal/private"**.
  - other concrete CIDR/host (incl. public IPs) → **"a specific host/range"** (public → broad).
  - **ipset/alias reference** (`+name`, `dc/name`, or any non-IP token) → **"unknown breadth (named
    set/alias — membership not resolved in v1)"** → treated **conservatively (never low)**.
- **Port sensitivity** (`_port_label`): map well-known admin/mgmt ports → service + sensitivity:
  22 SSH, 8006 PVE-API, 3389 RDP, 5900-5999 VNC, 23 telnet, 3306 MySQL, 5432 Postgres, 6379 Redis,
  etc. `dport` may be a single port, a range (`8000:8100`), a comma list, or a service name —
  parse leniently; an unrecognized form is **not** downgraded to benign.
- **THE under-flag guards (advisor):**
  - **empty `dport` → ALL ports** → **maximal reach**, never low/unknown. `ACCEPT/in source=None
    dport=None` ⇒ *"permits ALL ports from anywhere"*, severity **HIGH**.
  - **empty `proto`** → all protocols (does not narrow).
  - **`enable=0`** → classify as **"staged, not active"** (not "permits"/"blocks"); risk floor only.
- **Action × direction:**
  - `ACCEPT` + `in` → **permits** dport from source. Severity = f(breadth, port-sensitivity):
    anywhere → HIGH; anywhere + mgmt port → HIGH (loud); internal → MEDIUM; single host → LOW/MEDIUM.
  - `DROP`/`REJECT` + `in` → **blocks** dport from source. If it blocks a management port (22/8006)
    from a broad source → **lockout-risk HIGH** (could cut management access).
  - `out` → egress note (lower severity; "permits/blocks outbound …").

**Output** (`FirewallReachResult`): `summary_lines`, `affected` (list of dicts), `risk`,
`risk_reasons`, `complete`. `affected` entry:

```python
{
  "effect": "permits" | "blocks" | "staged",
  "service": "SSH (22/tcp)" | "port 8080/tcp" | "ALL ports",
  "from": "0.0.0.0/0 (the entire internet)" | "10.0.0.0/8 (internal)" | "named set +mgmt",
  "direction": "in" | "out",
  "scope": "<scope_label>",
  "severity": "high" | "medium" | "low",
}
```

Every summary line is rule-scoped ("this rule permits …"); the result carries the standing disclaimer
*"per-rule reach — effect depends on the full ordered ruleset, default policy, and whether the
firewall is enabled for this scope."*

**Wiring:**
- `plan_firewall_rule_add(...)` → gains `api` ONLY to pull `cfg`? No — `mgmt_host` is derivable without
  the rule plan reading the API; pass it from the server tool (which has `cfg`). To keep the factory
  pure, the **server tool** extracts `mgmt_host` from `cfg.api_base_url` and passes it into the plan
  builder, which forwards it to `compute_firewall_reach`. (Alternatively `plan_firewall_rule_add`
  stays pure and `mgmt_host` defaults None — the self-lockout hint is then omitted, still honest.)
  **Decision:** keep `plan_firewall_rule_add` pure; thread `mgmt_host` from the server tool as an
  optional arg. v1 may pass None (self-lockout hint is a nicety, not load-bearing).
- `plan_firewall_rule_remove` / `plan_firewall_rule_update` already read the rule; run
  `compute_firewall_reach` on the rule being removed/changed → *"removing this ACCEPT closes <service>
  to <from>"* / *"removing this DROP re-permits <service>"* / update = before/after reach delta.

## Part B — best-effort mgmt-interface naming on an unconditional HIGH

`plan_network_apply` is already `RISK_HIGH` unconditional, so naming the interface **structurally
cannot under-flag** — it only adds specificity. `compute_apply_lockout(pending_ifaces, mgmt_host,
ifaces)` (pure) returns which pending interface(s) carry the management host.

- `mgmt_host` = host component of `cfg.api_base_url`. **Honest caveat (advisor):** this is often a
  **hostname** (`pve.example.lan`), which won't match an iface `address` — and the mgmt IP may live on
  a bond/VLAN *under* the bridge. So matching is **best-effort**: a hit → name it loudly (*"apply
  touches `vmbr0`, which holds the management host {mgmt} — you will lose SSH/API; recovery needs
  console"*); a miss / non-IP host / unreadable → *"could not identify the management interface — HIGH
  stands; assume lockout risk."* **Never** "no lockout."
- `plan_network_apply` reads `network_list` (already does) + passes `mgmt_host` from cfg → engine.
- `plan_sdn_apply`: lighter touch — SDN apply rarely carries the mgmt path (usually on a vmbr, not an
  SDN vnet). Add the same best-effort note where cheap; do NOT block A on SDN depth.

## Honesty contract

- **Per-rule reach, never "cluster exposed" as fact** (the framing above).
- **Missing field → maximal, never benign:** empty dport → ALL ports; empty source → anywhere;
  ipset/alias → unknown-conservative; empty proto → all protocols.
- **`enable=0` → staged-inert** ("staged, not active").
- **B cannot lower the HIGH floor;** non-identification → HIGH stands, never "no lockout."
- **`complete`** propagates (Plan field, shipped with the storage class). A read failure in B →
  complete=False + disclosure; the pure reach engine is complete by construction (no reads) but a
  malformed input it cannot parse must surface as conservative, not benign.
- Risk only ever raised, never lowered.

## Output contract

Reuses the shipped additive `Plan.affected: list[dict]` + `Plan.complete: bool` (no contract change).
`as_dict` + `_record_plan` already serialize both. The firewall rule tools and `network_apply` are
**MCP-only** (`pve_firewall_rule_*` and `network_apply` are in `EXCLUDED_FROM_SLICE`/not in the A2A
slice), so `affected` surfaces via the MCP response + the PROVE ledger, not A2A — same honest scope as
the prior two classes.

## Files

- **Edit:** `src/proximo/blast.py` — add `compute_firewall_reach(...)` + `FirewallReachResult` +
  `_source_breadth` / `_port_label` helpers (Part A); add `compute_apply_lockout(...)` +
  `_iface_holding_host(...)` (Part B). All PURE.
- **Edit:** `src/proximo/firewall.py` — `plan_firewall_rule_add` / `remove` / `update` call
  `compute_firewall_reach`, prepend its lines, set `affected` + `complete`, `_max_risk`-escalate
  (never lower the MEDIUM floor).
- **Edit:** `src/proximo/network.py` — `plan_network_apply` (and lightly `plan_sdn_apply`) call
  `compute_apply_lockout`, name the iface, set `affected` + `complete` (HIGH stays).
- **Edit:** `src/proximo/server.py` — thread `mgmt_host` (from `cfg.api_base_url`) into the firewall
  rule_add plan lambda if the pure-factory-with-optional-arg path is chosen.
- **New:** `tests/test_blast_firewall.py` — pure engine unit tests (A + B).
- **Edit:** `tests/test_firewall.py` / `tests/test_network.py` — update the existing rule/apply plan
  tests for the enriched output (behavior preserved; assert structured `affected`).
- **New:** `scripts/live-smoke/fw-reach-smoke.py` — read-only PLAN reach check.

## Testing (TDD)

Pure-engine (A), zero API:
- **`ACCEPT/in, source=None, dport=None, proto=None` → maximal HIGH "permits ALL ports from anywhere"**
  (the advisor's separating test — write FIRST).
- `ACCEPT/in dport=22 source=0.0.0.0/0` → HIGH, "permits SSH (22/tcp) from the entire internet".
- `ACCEPT/in dport=22 source=10.0.0.0/8` → MEDIUM (internal).
- `ACCEPT/in dport=8080 source=203.0.113.5` → LOW/MEDIUM (single host).
- `ACCEPT/in source=+admins` (ipset) → unknown-breadth, conservative (not low).
- `DROP/in dport=22 source=0.0.0.0/0` → blocks SSH broadly → lockout-risk HIGH.
- `enable=0` ACCEPT/in anywhere → "staged, not active", not "permits".
- `out` direction → egress note, lower severity.
- dport range (`8000:8100`) / comma list (`80,443`) → parsed, not downgraded.

Pure-engine (B), zero API:
- pending iface `vmbr0` with address matching mgmt IP → named lockout entry, HIGH.
- mgmt_host is a hostname (no match) → "could not identify mgmt interface — HIGH stands".
- mgmt iface read absent → best-effort miss, HIGH stands, never "no lockout".

Seam (fake api, mirrors `test_blast_seam.py`): `pve_firewall_rule_add` dry-run → `resp["affected"]`
carries the reach; ledger `planned` entry carries `affected`. `pve_network_apply` dry-run → names the
iface when matchable; HIGH always.

Full suite stays green (currently 2172); ruff + pyright clean. Independent 3-lens redteam
(correctness/under-flag · honesty/per-rule-reach-not-cluster-exposed · leak) before "done", then a
read-only live reach smoke on x3650.

## Sequencing (advisor)

Build **Part A to completion** (engine + wired into all three rule plans + tested + its own redteam +
committed) **before** starting Part B — so if the combined work runs long, A is a clean shippable
stopping point and B's I/O-shape uncertainty cannot stall it.

## Non-goals / deferred

- Full ordered-ruleset effective-exposure resolution (whole ruleset + default policy).
- Firewall-enabled-state read (covered by the per-rule-reach disclaimer).
- ipset/alias → concrete CIDR resolution (named, not resolved, in v1).
- Deep SDN-apply lockout modeling (vnet/zone carrying mgmt — rare; light touch only).

## Open / smoke-confirm

- Confirm PVE firewall rule fields at the live API: `dport`/`sport` forms (port, range `a:b`, list),
  `source`/`dest` forms (CIDR, ipset `+name`, alias `dc/name`), `enable` 1/0, `proto`.
- Confirm `network_list` per-iface `address`/`cidr` field names + that the mgmt host can be matched
  (IP vs hostname); keep the best-effort/HIGH-stands fallback regardless.
