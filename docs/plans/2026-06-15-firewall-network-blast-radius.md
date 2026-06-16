# Firewall/Network Blast-radius Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compute per-rule firewall REACH ("this rule permits 22/tcp from 0.0.0.0/0") and best-effort name the management interface a network apply would drop — surfaced as structured `affected` + recorded to the PROVE ledger.

**Architecture:** Pure engines in `blast.py` (`compute_firewall_reach`, `compute_apply_lockout`); the existing `plan_firewall_rule_*` / `plan_network_apply` factories gather any reads and delegate — mirroring the shipped storage + ACL classes. **Build Part A to completion before Part B** (A is a clean shippable stopping point).

**Tech Stack:** Python 3.12+, dataclasses, stdlib `ipaddress`/`re`. Tests via `uv run python -m pytest`.

**Spec:** `docs/specs/2026-06-15-firewall-network-blast-radius.md`. **Branch:** `feat/firewall-network-blast-radius`.

**Commands (Proximo's own venv):** `uv run python -m pytest <path> -q` · `uv run ruff check src tests` · `uv run pyright`

**THE load-bearing framing (every task):** per-rule REACH, never "cluster exposed" as fact. Missing field → MAXIMAL, never benign (empty dport → ALL ports; empty source → anywhere; ipset/alias → unknown-conservative). `enable=0` → "staged, not active". Risk only raised, never lowered. `Plan.affected` + `Plan.complete` already exist (shipped with storage class) — reuse, no contract change.

---

## PART A — firewall reach (build to completion first)

### Task A1: source-breadth + port-label helpers (pure)

**Files:** Modify `src/proximo/blast.py`; Test `tests/test_blast_firewall.py` (new).

- [ ] **Step 1: Write failing tests** — create `tests/test_blast_firewall.py`:

```python
"""Firewall/network reach engine — pure unit tests (zero API)."""
from __future__ import annotations

from proximo.blast import _port_label, _source_breadth


def test_source_breadth_anywhere():
    for s in (None, "", "0.0.0.0/0", "::/0"):
        kind, _ = _source_breadth(s)
        assert kind == "anywhere", s


def test_source_breadth_internal():
    for s in ("10.0.0.0/8", "192.168.1.0/24", "172.16.5.4", "127.0.0.1"):
        assert _source_breadth(s)[0] == "internal", s


def test_source_breadth_specific_public():
    assert _source_breadth("203.0.113.5")[0] == "host"
    assert _source_breadth("8.8.8.0/24")[0] == "range"


def test_source_breadth_ipset_alias_is_unknown():
    for s in ("+admins", "dc/trusted", "myalias"):
        assert _source_breadth(s)[0] == "named", s


def test_port_label_known_and_unknown():
    assert "SSH" in _port_label("22") and "22" in _port_label("22")
    assert "8006" in _port_label("8006")
    assert _port_label(None) == "ALL ports"
    assert _port_label("") == "ALL ports"
    assert "8080" in _port_label("8080")
    assert "8000:8100" in _port_label("8000:8100")
```

- [ ] **Step 2: Run → FAIL** (`ImportError`): `uv run python -m pytest tests/test_blast_firewall.py -q`

- [ ] **Step 3: Implement** — append to `blast.py`:

```python
# ===========================================================================
# Firewall / network reach class.
# ===========================================================================

import ipaddress as _ipaddress

# Well-known admin/management ports -> (service label, is_sensitive).
_SENSITIVE_PORTS: dict[int, str] = {
    22: "SSH", 8006: "PVE API", 3389: "RDP", 23: "telnet", 3306: "MySQL",
    5432: "Postgres", 6379: "Redis", 27017: "MongoDB", 9200: "Elasticsearch",
    2375: "Docker API", 2376: "Docker API (TLS)", 111: "rpcbind", 445: "SMB",
}


def _source_breadth(source: str | None) -> tuple[str, str]:
    """(kind, human) for a rule source. kind in {anywhere, internal, host, range, named}.
    None/empty/0.0.0.0/0/::/0 => anywhere (widest). RFC1918/loopback/link-local => internal.
    A concrete public host => host; public CIDR => range. Non-IP token (ipset +name / alias
    dc/name) => named (unknown breadth — never treated as narrow)."""
    s = (source or "").strip()
    if s in ("", "0.0.0.0/0", "::/0"):
        return "anywhere", "0.0.0.0/0 (the entire internet/WAN)"
    try:
        net = _ipaddress.ip_network(s, strict=False)
    except ValueError:
        return "named", f"{s} (named set/alias — membership not resolved)"
    if net.is_private or net.is_loopback or net.is_link_local:
        return "internal", f"{s} (internal/private)"
    if net.num_addresses == 1:
        return "host", f"{s} (a single host)"
    return "range", f"{s} (a public range)"


def _port_label(dport: str | None) -> str:
    """Human label for a dport. Empty => ALL ports (maximal — NEVER benign). Recognizes a single
    well-known port; passes ranges/lists/service-names through verbatim (not downgraded)."""
    d = (dport or "").strip()
    if not d:
        return "ALL ports"
    if d.isdigit():
        svc = _SENSITIVE_PORTS.get(int(d))
        return f"{svc} ({d}/tcp)" if svc else f"port {d}/tcp"
    return f"port(s) {d}"


def _port_is_sensitive(dport: str | None) -> bool:
    d = (dport or "").strip()
    if not d:
        return True   # ALL ports includes the sensitive ones
    return d.isdigit() and int(d) in _SENSITIVE_PORTS
```

- [ ] **Step 4: Run → PASS** + `uv run ruff check src/proximo/blast.py tests/test_blast_firewall.py`

- [ ] **Step 5: Commit** — `git add src/proximo/blast.py tests/test_blast_firewall.py && git commit -m "feat(fw): source-breadth + port-label reach helpers (pure)"`

---

### Task A2: `compute_firewall_reach` aggregator

**Files:** Modify `src/proximo/blast.py`; Test `tests/test_blast_firewall.py`.

- [ ] **Step 1: Write failing tests** (the FIRST is the advisor's separating test):

```python
from proximo.blast import compute_firewall_reach


def test_accept_in_no_source_no_dport_is_maximal_high():
    r = compute_firewall_reach("ACCEPT", "in", source=None, dport=None, proto=None,
                               scope_label="cluster")
    assert r.risk == "high"
    a = r.affected[0]
    assert a["effect"] == "permits" and a["service"] == "ALL ports"
    assert a["from"].startswith("0.0.0.0/0") and a["severity"] == "high"


def test_accept_in_ssh_from_internet_high():
    r = compute_firewall_reach("ACCEPT", "in", source="0.0.0.0/0", dport="22", proto="tcp",
                               scope_label="cluster")
    assert r.risk == "high"
    assert any("SSH" in a["service"] and a["severity"] == "high" for a in r.affected)


def test_accept_in_ssh_from_internal_medium():
    r = compute_firewall_reach("ACCEPT", "in", source="10.0.0.0/8", dport="22", proto="tcp",
                               scope_label="cluster")
    assert any(a["severity"] == "medium" for a in r.affected)
    assert r.risk in ("medium", "high")  # never below medium for an internal mgmt-port open


def test_drop_in_mgmt_port_broad_is_lockout_high():
    r = compute_firewall_reach("DROP", "in", source="0.0.0.0/0", dport="8006", proto="tcp",
                               scope_label="cluster")
    assert r.risk == "high"
    assert any(a["effect"] == "blocks" for a in r.affected)
    assert any("lockout" in line.lower() for line in r.summary_lines)


def test_enable_zero_is_staged_not_permits():
    r = compute_firewall_reach("ACCEPT", "in", source="0.0.0.0/0", dport=None, proto=None,
                               scope_label="cluster", enable=False)
    assert any(a["effect"] == "staged" for a in r.affected)
    assert any("staged" in line.lower() for line in r.summary_lines)


def test_ipset_source_conservative_not_low():
    r = compute_firewall_reach("ACCEPT", "in", source="+admins", dport="22", proto="tcp",
                               scope_label="cluster")
    assert all(a["severity"] != "low" for a in r.affected)  # unknown breadth -> not low
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** — append to `blast.py`:

```python
@dataclass
class FirewallReachResult:
    summary_lines: list[str]
    affected: list[dict]
    risk: str
    risk_reasons: list[str]
    complete: bool = True


_REACH_DISCLAIMER = (
    "PER-RULE REACH: this describes what THIS rule permits/blocks if it is the deciding match in an "
    "enforced, default-DROP firewall — NOT whether the cluster is actually exposed (that depends on "
    "the full ordered ruleset, the default policy, and whether the firewall is enabled for this scope)."
)


def compute_firewall_reach(
    action: str,
    direction: str,
    source: str | None,
    dport: str | None,
    proto: str | None,
    scope_label: str,
    enable: bool = True,
    mgmt_host: str | None = None,
) -> FirewallReachResult:
    """PURE per-rule reach classification. No API. See _REACH_DISCLAIMER for the framing contract."""
    action = (action or "").upper()
    breadth, from_label = _source_breadth(source)
    service = _port_label(dport)
    sensitive = _port_is_sensitive(dport)
    lines: list[str] = [_REACH_DISCLAIMER]
    reasons: list[str] = ["per-rule reach is heuristic; absence of HIGH is not a safety signal"]
    affected: list[dict] = []
    risk = RISK_MEDIUM

    if not enable:
        lines.append(f"this rule is DISABLED (enable=0) — STAGED, not active: would {action.lower()} "
                     f"{service} from {from_label} ({direction}) only once enabled")
        affected.append({"effect": "staged", "service": service, "from": from_label,
                         "direction": direction, "scope": scope_label, "severity": "low"})
        return FirewallReachResult(summary_lines=lines, affected=affected, risk=risk,
                                   risk_reasons=reasons + ["rule is staged (enable=0)"])

    if direction == "out":
        verb = "permits" if action == "ACCEPT" else "blocks"
        lines.append(f"this rule {verb} OUTBOUND {service} to {from_label} (egress — lower exposure)")
        affected.append({"effect": "permits" if action == "ACCEPT" else "blocks", "service": service,
                         "from": from_label, "direction": "out", "scope": scope_label,
                         "severity": "low"})
        return FirewallReachResult(summary_lines=lines, affected=affected, risk=risk,
                                   risk_reasons=reasons)

    # direction == in
    if action == "ACCEPT":
        if breadth == "anywhere":
            sev = "high"
        elif breadth in ("range", "named"):
            sev = "high" if sensitive else "medium"
        elif breadth == "internal":
            sev = "medium"
        else:  # host
            sev = "medium" if sensitive else "low"
        lines.append(f"this rule PERMITS inbound {service} from {from_label} on {scope_label}")
        if sev == "high":
            lines.append(f"  -> reachable from {from_label}"
                         + (" on a management/admin service" if sensitive else ""))
        affected.append({"effect": "permits", "service": service, "from": from_label,
                         "direction": "in", "scope": scope_label, "severity": sev})
        risk = _max_risk(risk, RISK_HIGH) if sev == "high" else risk
    else:  # DROP / REJECT, in
        lockout = sensitive and breadth in ("anywhere", "range", "named", "internal")
        lines.append(f"this rule BLOCKS inbound {service} from {from_label} on {scope_label}")
        sev = "medium"
        if lockout:
            sev = "high"
            lines.append("  -> LOCKOUT RISK: blocks a management/admin port from a broad source; "
                         "if this covers your access path you lose SSH/API (console to recover)")
            risk = _max_risk(risk, RISK_HIGH)
        affected.append({"effect": "blocks", "service": service, "from": from_label,
                         "direction": "in", "scope": scope_label, "severity": sev})

    return FirewallReachResult(summary_lines=lines, affected=affected, risk=risk, risk_reasons=reasons)
```

- [ ] **Step 4: Run → PASS** + ruff.
- [ ] **Step 5: Commit** — `git commit -am "feat(fw): compute_firewall_reach — per-rule reach + under-flag guards (pure)"`

---

### Task A3: wire into `plan_firewall_rule_add`

**Files:** Modify `src/proximo/firewall.py` (`plan_firewall_rule_add` `:427-476`); Test `tests/test_firewall.py`.

- [ ] **Step 1: Failing test** in `tests/test_firewall.py` (match existing fakes there):

```python
def test_plan_firewall_rule_add_names_reach():
    from proximo.firewall import plan_firewall_rule_add
    plan = plan_firewall_rule_add("ACCEPT", "in", "cluster", source="0.0.0.0/0", dport="22")
    assert plan.affected and plan.affected[0]["effect"] == "permits"
    assert plan.risk == RISK_HIGH
    assert any("PERMITS inbound" in line for line in plan.blast_radius)
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** — in `plan_firewall_rule_add`, after the validation + `scope_label`, call the engine and merge (keep the generic floor strings, prepend reach, set affected, `_max_risk`). Add `from . import blast` to firewall.py imports; import `_max_risk` from `.planning`. Replace the `return Plan(...)`:

```python
    reach = blast.compute_firewall_reach(action, direction, scope_label_kind(scope, node, vmid, kind)
                                         if False else action and action,  # placeholder — see note
                                         ...)
```

> NOTE for the implementer: call `blast.compute_firewall_reach(action, direction, source, dport, proto,
> scope_label=scope_label, enable=True)`. (rule_add has no `proto` param today — pass `proto=None`, or
> add a `proto` passthrough if the tool exposes it; check `firewall_rule_add` signature first.) Then:

```python
    reach = blast.compute_firewall_reach(action, direction, source, dport, None, scope_label)
    return Plan(
        action="pve_firewall_rule_add",
        target=f"firewall/{scope}",
        change=f"add firewall rule on {scope_label}: {rule_summary}",
        current={},
        blast_radius=reach.summary_lines + [
            f"adds a firewall rule to {scope_label}: {rule_summary}",
            "rule is appended — positions of existing rules are not shifted",
            "no UNDO: firewall config is not in guest snapshots; revert by removing this rule",
        ],
        affected=reach.affected,
        risk=_max_risk(RISK_MEDIUM, reach.risk),
        risk_reasons=reach.risk_reasons,
        complete=reach.complete,
    )
```

- [ ] **Step 4: Run → PASS** (`tests/test_firewall.py`) + ruff.
- [ ] **Step 5: Commit** — `git commit -am "feat(fw): plan_firewall_rule_add computes per-rule reach"`

---

### Task A4: wire into `plan_firewall_rule_remove` + `plan_firewall_rule_update`

**Files:** Modify `src/proximo/firewall.py`; Test `tests/test_firewall.py`.

- [ ] **Step 1: Failing tests** — removing an ACCEPT names what it CLOSES; removing a DROP names what it RE-PERMITS:

```python
def test_plan_firewall_rule_remove_names_what_closes(_fw_remove_api_with_accept_22):
    # fake api returns a rule at pos: ACCEPT in dport=22 source=0.0.0.0/0
    plan = plan_firewall_rule_remove(_fw_remove_api_with_accept_22, 0, "cluster")
    assert any("clos" in line.lower() or "no longer permit" in line.lower() for line in plan.blast_radius)
    assert plan.affected  # carries the reach of the rule being removed
```

(Build the fake to return the rule fields from `firewall_rules_list`; mirror the existing
`plan_firewall_rule_remove` tests in `tests/test_firewall.py`.)

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** — in `plan_firewall_rule_remove`, when a rule is found, run
  `blast.compute_firewall_reach(found["action"], found.get("type","in"), found.get("source"),
  found.get("dport"), found.get("proto"), scope_label, enable=bool(found.get("enable",1)))` and frame
  the removal: an ACCEPT removed → "removing this rule CLOSES " + reach service/from; a DROP removed →
  "removing this rule RE-PERMITS " + reach service/from. Set `affected=reach.affected`,
  `complete` per the read. For `plan_firewall_rule_update`, compute reach of the post-update rule
  (merge `new_fields` over the current rule) and surface the before/after delta. Keep the MEDIUM floor;
  `_max_risk` with reach.risk.

- [ ] **Step 4: Run → PASS** + ruff.
- [ ] **Step 5: Commit** — `git commit -am "feat(fw): rule remove/update surface per-rule reach (close/re-permit/delta)"`

---

### Task A5: Part-A gate + seam + redteam (clean shippable stopping point)

- [ ] **Step 1:** `uv run ruff check src tests && uv run pyright && uv run python -m pytest -q` — all green.
- [ ] **Step 2: Seam test** in `tests/test_blast_seam.py`: `pve_firewall_rule_add` dry-run → `resp["affected"]` carries reach; ledger `planned` entry carries `affected`. (Mirror the existing seam fakes.)
- [ ] **Step 3: CHANGELOG** `[Unreleased]` → Added: per-rule firewall reach (Part A).
- [ ] **Step 4: Independent 3-lens redteam** over the A diff: correctness/under-flag (empty dport/source, ipset, ranges, IPv6, enable=0); honesty (per-rule-reach phrasing — never "cluster exposed" as fact; never lower MEDIUM floor); leak (generic fixtures). Apply findings test-first; re-gate.
- [ ] **Step 5: Commit.** Part A is now shippable on its own.

---

## PART B — network-apply lockout naming (after A is complete)

### Task B1: `compute_apply_lockout` + `_iface_holding_host` (pure)

**Files:** Modify `src/proximo/blast.py`; Test `tests/test_blast_firewall.py`.

- [ ] **Step 1: Failing tests:**

```python
from proximo.blast import compute_apply_lockout


def test_apply_lockout_names_iface_holding_mgmt_ip():
    pending = ["vmbr0"]
    ifaces = [{"iface": "vmbr0", "address": "10.0.0.10"}, {"iface": "vmbr1", "address": "10.0.0.1"}]
    r = compute_apply_lockout(pending, "10.0.0.10", ifaces)
    assert r.risk == "high"
    assert any(a.get("iface") == "vmbr0" for a in r.affected)
    assert any("10.0.0.10" in line for line in r.summary_lines)


def test_apply_lockout_hostname_mgmt_no_match_high_stands():
    r = compute_apply_lockout(["vmbr0"], "pve.example.lan",
                              [{"iface": "vmbr0", "address": "10.0.0.10"}])
    assert r.risk == "high"
    assert any("could not identify" in line.lower() for line in r.summary_lines)
    assert not any(a.get("severity") == "low" for a in r.affected)  # never "no lockout"
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** — append to `blast.py`:

```python
@dataclass
class ApplyLockoutResult:
    summary_lines: list[str]
    affected: list[dict]
    risk: str
    risk_reasons: list[str]
    complete: bool = True


def _iface_holding_host(host: str | None, ifaces: list[dict]) -> str | None:
    """Best-effort: the iface whose address/cidr equals the mgmt host IP. None if host is not an IP,
    no iface matches, or addresses are absent (best-effort — caller keeps HIGH regardless)."""
    h = (host or "").strip()
    try:
        target = _ipaddress.ip_address(h)
    except ValueError:
        return None
    for i in ifaces:
        for key in ("address", "cidr", "address6"):
            val = (i.get(key) or "").split("/")[0].strip()
            if not val:
                continue
            try:
                if _ipaddress.ip_address(val) == target:
                    return i.get("iface")
            except ValueError:
                continue
    return None


def compute_apply_lockout(pending_ifaces: list[str], mgmt_host: str | None,
                          ifaces: list[dict]) -> ApplyLockoutResult:
    """PURE. Best-effort naming on top of an UNCONDITIONAL HIGH (network apply is always RISK_HIGH).
    Names the pending iface that carries the mgmt host; non-identification => HIGH stands, never 'safe'."""
    mgmt_iface = _iface_holding_host(mgmt_host, ifaces)
    lines: list[str] = []
    affected: list[dict] = []
    reasons = ["network apply can lose connectivity; no automatic rollback (console to recover)"]
    if mgmt_iface and mgmt_iface in pending_ifaces:
        lines.append(f"LOCKOUT: this apply changes {mgmt_iface!r}, which holds the management host "
                     f"{mgmt_host} — you will lose SSH/API access; recovery needs console/physical")
        affected.append({"iface": mgmt_iface, "effect": "management interface changing",
                         "holds": mgmt_host, "severity": "high"})
        reasons.append(f"pending change to {mgmt_iface} (management interface) — lockout")
    elif mgmt_iface:
        lines.append(f"management host {mgmt_host} is on {mgmt_iface!r}, which is NOT in the pending "
                     "set — but apply is still RISK_HIGH (a dependent bond/VLAN may be affected)")
    else:
        lines.append(f"could not identify the management interface (mgmt host {mgmt_host!r} is a "
                     "hostname or did not match any iface address) — RISK_HIGH stands; assume lockout risk")
    return ApplyLockoutResult(summary_lines=lines, affected=affected, risk=RISK_HIGH,
                              risk_reasons=reasons)
```

- [ ] **Step 4: Run → PASS** + ruff.
- [ ] **Step 5: Commit** — `git commit -am "feat(net): compute_apply_lockout — best-effort mgmt-iface naming (pure)"`

---

### Task B2: wire into `plan_network_apply` (+ light `plan_sdn_apply`)

**Files:** Modify `src/proximo/network.py`; Test `tests/test_network.py`.

- [ ] **Step 1: Failing test** — `plan_network_apply` with a fake api whose `network_list` returns
  `vmbr0` (pending) holding the mgmt IP, and cfg.api_base_url with that IP → names vmbr0, HIGH.

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** — in `plan_network_apply`, after reading `ifaces` (already done), derive
  `mgmt_host` from `api.config.api_base_url` (parse host: `urllib.parse.urlsplit("//"+...).hostname`
  or strip scheme/port), collect `pending = [i["iface"] for i in ifaces if i.get("pending") or
  i.get("changes")]`, call `blast.compute_apply_lockout(pending, mgmt_host, ifaces)`, prepend its lines,
  set `affected=lockout.affected`. Risk stays `RISK_HIGH`. On read failure keep the existing HIGH +
  `complete=False`. For `plan_sdn_apply`: add a one-line note that mgmt is rarely on an SDN vnet; no
  deep modeling.

- [ ] **Step 4: Run → PASS** + ruff + pyright + full suite.
- [ ] **Step 5: Commit** — `git commit -am "feat(net): plan_network_apply names the mgmt interface (best-effort, HIGH stays)"`

---

### Task B3: full gate + CHANGELOG + live-smoke + redteam

- [ ] **Step 1:** `uv run ruff check src tests && uv run pyright && uv run python -m pytest -q` — green.
- [ ] **Step 2: CHANGELOG** `[Unreleased]` → add Part B (mgmt-iface naming on apply).
- [ ] **Step 3: Live-smoke** `scripts/live-smoke/fw-reach-smoke.py` — read-only: build a rule from env
  (`PROXIMO_FW_ACTION/DIRECTION/SOURCE/DPORT`), call `plan_firewall_rule_add`, print reach + affected.
- [ ] **Step 4: Independent 3-lens redteam** over the full diff (A+B). Apply findings test-first; re-gate.
  Then run the read-only reach smoke on x3650.
- [ ] **Step 5: Commit.**

---

## Self-Review

**Spec coverage:** reach helpers (A1) ✅ · reach aggregator + under-flag guards (A2) ✅ · rule_add wiring (A3) ✅ · rule_remove/update wiring (A4) ✅ · A gate/seam/redteam (A5) ✅ · lockout engine (B1) ✅ · network_apply wiring (B2) ✅ · gate/CHANGELOG/smoke/redteam (B3) ✅ · per-rule-reach framing in every reach string ✅ · empty-field=maximal (A2 first test) ✅ · B can't lower HIGH (B1) ✅ · `affected`+`complete` reuse ✅ · A-before-B sequencing ✅.

**Placeholder scan:** A3 Step 3 has a NOTE flagging the `proto` passthrough check + a placeholder line the implementer must replace with the real `compute_firewall_reach(...)` call shown directly below it — verify `firewall_rule_add`'s real param list (source/dport present; proto may need adding) before wiring. All other steps have complete code.

**Type consistency:** `compute_firewall_reach(action,direction,source,dport,proto,scope_label,enable,mgmt_host) -> FirewallReachResult{summary_lines,affected,risk,risk_reasons,complete}`; `compute_apply_lockout(pending_ifaces,mgmt_host,ifaces) -> ApplyLockoutResult{...}`; affected keys consistent across tasks + spec.
