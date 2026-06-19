# Spec — firewall-lockout blast-radius (coverage op-class #7, rank 2)

## Context
From the 2026-06-19 coverage audit. `plan_firewall_set_enabled` and `plan_firewall_options_set` are
both RISK_HIGH and *warn* "if ACCEPT rules for SSH(22)/PVE(8006) are absent the default-DROP policy
will lock you out" — but neither **reads the rules** to compute whether such a rule exists. Two tools,
one consequence graph. Enabling the firewall (or setting `policy_in=DROP`) under default-DROP locks out
management on every node whose ruleset lacks an inbound management ACCEPT — a fleet-wide cross-resource
consequence that today is only a generic string.

## The cross-resource graph
- `scope="cluster"` enable / `policy_in=DROP` → affects EVERY node. A node's host management (SSH 22 /
  PVE 8006) survives only if an inbound ACCEPT exists in (datacenter ∪ that node's) ruleset.
- `scope="node"` → that one node (still datacenter ∪ node rules).
- `scope="guest"` → self-scoped (loses access to THAT guest's services); NOT a fleet lockout → keep the
  existing generic HIGH warning, do NOT run the node engine.

## `compute_firewall_lockout_blast` — pure engine (blast.py)
Inputs (already-fetched): `nodes: list[str] | None` (None = node enumeration failed),
`datacenter_rules: list[dict] | None` (None = read failed), `node_rules: dict[node -> list|None]`.

### "Protective management ACCEPT" predicate (soundness — never count a non-protective rule)
A combined rule (datacenter ∪ node) protects management iff ALL hold:
- `enable` is not 0/"0" (a DISABLED rule offers no protection),
- `type` == "in" (management access is inbound),
- `action` == "ACCEPT",
- proto ∈ {"", "tcp", "any", "all"} (SSH/8006 are tcp — a udp/22 rule does NOT protect),
- dport covers 22 or 8006, OR is empty (ALL ports).

Among the protective rules for a node, take the WIDEST source breadth (`_source_breadth`): anywhere >
internal > host/range/named. Classify each node:
- **no protective rule** → LOCKOUT (high, named): "no inbound management ACCEPT (22/8006) found".
- **widest = host/range/named** → CONDITIONAL LOCKOUT (high, named): "management ACCEPT exists but
  source-restricted to <X> — if your admin source is not within it, ENABLING locks you out".
- **widest = internal** → disclosed, NOT named lockout: "management ACCEPT restricted to internal/private
  sources — protective only if you manage from inside the private network".
- **widest = anywhere** → disclosed, NOT named lockout: "open inbound management ACCEPT exists (rule #N)".
- **rules unreadable for that node** (datacenter or node None) → INCOMPLETE for that node → complete=False,
  treated as lockout-risk (conservative, named), never "safe".

### Risk posture (mirror compute_apply_lockout)
The op is RISK_HIGH **unconditional** (both plan functions already set HIGH on enable/policy). The engine
NEVER lowers it; it returns `max_severity="high"` for any triggering change and NAMES the lockout-risk
nodes (the affected set). Non-identification (no nodes enumerable / all reads failed) → loud, HIGH stands,
"absence of a named lockout is not a safety signal". This is naming on top of an unconditional HIGH —
not a risk computation that could under-flag.

### gather_firewall_lockout_dependents(api, scope, node)
I/O, fail-closed: `datacenter_rules = firewall_rules_list(cluster)` (fail→None); nodes = (cluster →
`cluster_resources(type=node)` names, fail→None) | (node → [node]); `node_rules[n] =
firewall_rules_list(node=n)` (fail→None). Returns (nodes, datacenter_rules, node_rules).

## Wiring
- `plan_firewall_set_enabled`: when `enabled is True` AND scope ∈ {cluster, node} → run engine, append
  summary_lines to blast, set Plan.affected/complete. risk stays HIGH. DISABLE / guest scope → unchanged.
- `plan_firewall_options_set`: when the change is a lockout-trigger AND scope ∈ {cluster, node} → run engine.
  Trigger = `enable` set truthy, OR `policy_in` set to "DROP" (case-insensitive), OR "policy_in" in
  delete_keys (reverts to PVE default DROP). `policy_in=ACCEPT` is a WIDENING → NOT a trigger.

## Build discipline
TDD (failing test first) → 2-lens redteam (soundness / under-flag + honesty / leak) → full suite +
ruff + pyright.

## Deferred (logged, not silently dropped)
- The DISABLE / `policy→ACCEPT` **exposure** direction (strips protection → guests exposed) is a different
  graph ("name everything under scope" — low information); kept as the existing generic HIGH warning.
- Source-vs-actual-admin matching is heuristic (we don't know the admin's true source); internal-restricted
  is treated as protective-with-disclosure rather than named lockout (proportionality vs cry-wolf).
