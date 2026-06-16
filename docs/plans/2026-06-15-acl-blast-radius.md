# ACL Blast-radius Implementation Plan (access/ACL class)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring `pve_acl_modify`'s preview to the blast-radius contract — extract its shadow/widen reasoning into a pure `compute_acl_blast`, populate structured `affected`, complete the target's shadow via group-membership resolution (#1), and add who-else-can-reach context (#2) — under the per-principal honesty constraint.

**Architecture:** Pure `compute_acl_blast(...)` in `blast.py` (no API) holds all reasoning; `plan_acl_modify(api, …)` gathers the reads (acl_list + target groups + group members + token privsep) and delegates — mirroring the shipped storage class. Built **extract-first** (behavior-preserving refactor) then layered extensions so the ~30 existing tests stay green until intentionally updated.

**Tech Stack:** Python 3.12+, dataclasses. Reads: `access_acl_list` (access.py), `user_get`/`group_get` (access_users.py), `access_tokens_list` (access.py). Tests via `uv run python -m pytest`.

**Spec:** `docs/specs/2026-06-15-acl-blast-radius.md`. **Branch:** `feat/acl-blast-radius`.

**Commands (Proximo's own venv):** `uv run python -m pytest <path> -q` · `uv run ruff check src tests` · `uv run pyright`

**Per-principal honesty constraint (applies to EVERY task):** `acl_modify` targets user|token only. The **target** is the only principal whose access changes → only the target gets `gains`/`loses`. Who-else members are `unchanged` context, NEVER gains/loses. Risk is only ever raised, never lowered. Reads fail closed (caveat retained, never "absence = safe").

---

### Task 1: Extract the existing shadow/widen reasoning into a pure `compute_acl_blast` (behavior-preserving)

**Files:**
- Modify: `src/proximo/blast.py` (add `AclBlastResult` + `compute_acl_blast`)
- Modify: `src/proximo/access.py` (`plan_acl_modify` `:348-592` → gather read, delegate, build Plan)

This task moves logic; the ~30 existing `plan_acl_modify` tests in `tests/test_access.py` are the regression net — they must stay green with **no edits**.

- [ ] **Step 1: Add `AclBlastResult` + `compute_acl_blast` to `src/proximo/blast.py`**

Append to `blast.py`. The body is the EXISTING analysis from `access.py` `plan_acl_modify` (current lines ~395-572), moved verbatim, with two changes: (a) it receives `acl_entries: list | None` + `acl_error: str | None` instead of reading the api (None signals the read failed — preserving the `check_error` branch); (b) it returns an `AclBlastResult` instead of a `Plan`. `affected`/`complete` are added in later tasks (here: `affected=[]`, `complete=True`).

```python
@dataclass
class AclBlastResult:
    summary_lines: list[str]
    risk: str
    risk_reasons: list[str]
    current: dict
    affected: list[dict] = field(default_factory=list)
    complete: bool = True


def compute_acl_blast(
    path: str,
    roles: str,
    target: str,
    kind: str,
    delete: bool,
    acl_entries: list[dict] | None,   # None => the ACL read FAILED (fail-closed branch)
    acl_error: str | None = None,
) -> AclBlastResult:
    """PURE shadow/widen analysis for an ACL grant/revoke. No API. acl_entries is the current
    ACL (already fetched); None means the read failed -> RISK_HIGH disclosure, never 'safe'."""
    from .planning import RISK_HIGH, RISK_MEDIUM  # local import: blast.py must not hard-depend on risk consts at top

    new_roles = {r.strip() for r in roles.split(",")}
    action_word = "revoke" if delete else "grant"

    # --- the existing analysis, moved from plan_acl_modify ---
    check_error = acl_error if acl_entries is None else None
    entries = acl_entries or []

    current_direct_entries: list[dict] = []
    inherited_entries: list[dict] = []
    if check_error is None:
        for entry in entries:
            ugid = entry.get("ugid", "")
            entry_path = entry.get("path", "")
            entry_propagate = entry.get("propagate", True)
            if ugid != target:
                continue
            if entry_path == path:
                current_direct_entries.append(entry)
            elif path.startswith(entry_path.rstrip("/") + "/") and entry_propagate:
                inherited_entries.append(entry)

    inherited_roles: set[str] = {e.get("roleid", "") for e in inherited_entries}
    current_direct_roles: set[str] = {e.get("roleid", "") for e in current_direct_entries}
    has_direct = bool(current_direct_entries)
    effective_before: set[str] = current_direct_roles if has_direct else inherited_roles
    if not delete:
        effective_after = new_roles
    else:
        remaining_direct = current_direct_roles - new_roles
        effective_after = remaining_direct if remaining_direct else inherited_roles
    shadowed_inherited = inherited_roles - new_roles if not has_direct and not delete else set()
    widened = effective_after - effective_before

    blast: list[str] = []
    reasons: list[str] = []
    risk = RISK_MEDIUM

    if check_error is not None:
        blast.append(
            f"could NOT read current ACL ({check_error}) — cannot determine what privileges "
            "would be shadowed or widened; absence of a shadow/widen warning is NOT a safety signal"
        )
        reasons.append(
            "ACL read failed — shadow/widen analysis unavailable; absence of a warning is not a safety signal"
        )
        risk = RISK_HIGH
    else:
        group_entries_present = any(
            e.get("type") == "group" and (
                e.get("path") == path or path.startswith(e.get("path", "").rstrip("/") + "/")
            )
            for e in entries
        )
        if group_entries_present:
            blast.append(
                "UNCERTAINTY: group-type ACL entries exist at or above this path — "
                "group membership grants are NOT visible in the per-user ACL list; "
                "shadow/widen analysis may be INCOMPLETE for users who are group members"
            )
            reasons.append(
                "group-based ACL grants exist at this scope; shadow analysis may miss group-inherited privileges"
            )
        if not delete:
            if shadowed_inherited:
                sr = ", ".join(sorted(shadowed_inherited))
                blast.append(
                    f"SHADOW WARNING: granting {roles!r} at {path!r} will REPLACE {target!r}'s "
                    f"INHERITED grants — the following inherited roles will NO LONGER apply at "
                    f"{path!r}: {sr}. (The specific-path entry takes precedence over ancestor "
                    "propagated grants.)"
                )
                reasons.append(
                    "granting a specific-path ACL replaces ancestor inherited (propagated) grants — "
                    f"inherited roles {{{sr}}} are shadowed (lost) at {path!r}"
                )
                risk = RISK_HIGH
            if widened:
                wr = ", ".join(sorted(widened))
                blast.append(f"NEW privileges at {path!r}: {target!r} gains {wr}")
                reasons.append(f"target gains new roles: {wr}")
            if not shadowed_inherited and not widened:
                blast.append(
                    f"grants {roles!r} to {target!r} at {path!r} — "
                    "no inherited grants detected to shadow; no new privileges detected"
                )
                reasons.append("no inherited grants to shadow; grant is additive at this path")
        else:
            if widened:
                wr = ", ".join(sorted(widened))
                blast.append(
                    f"WIDEN WARNING: revoking the specific entry at {path!r} for {target!r} "
                    f"RESTORES inherited grants — {target!r} will gain back: {wr}"
                )
                reasons.append(
                    "revoking a specific-path ACL restores inherited grants — "
                    f"the following roles become effective again at {path!r}: {wr}"
                )
                risk = RISK_HIGH
            if not widened:
                blast.append(
                    f"revokes {roles!r} from {target!r} at {path!r} — no inherited grants detected "
                    "that would widen access after revoke"
                )
                reasons.append("no inherited grants detected; revoke is straightforward")

    if "Administrator" in new_roles:
        blast.append("Administrator role grants ALL Proxmox privileges — this is the widest possible role")
        reasons.append("Administrator = super-role with full cluster privileges")
        risk = RISK_HIGH
    if path in ("/", "/storage"):
        blast.append(f"ACL at {path!r} affects ALL resources at that scope on the cluster")
        reasons.append(f"path {path!r} is a high-blast scope (root or storage-wide)")
        risk = RISK_HIGH

    if not current_direct_entries:
        current: dict = {}
    else:
        first = current_direct_entries[0]
        current = {k: first[k] for k in ("path", "roleid", "ugid", "propagate") if k in first}

    return AclBlastResult(summary_lines=blast, risk=risk, risk_reasons=reasons, current=current)
```

- [ ] **Step 2: Rewrite `plan_acl_modify` in `src/proximo/access.py` to gather + delegate**

Replace the body AFTER the input validation (current lines ~395 through the `return Plan(...)` at ~592) with the gather-and-delegate version. KEEP the validation block (lines ~380-393) unchanged. Add `from . import blast` to the imports if not present.

```python
    # ... (keep the existing validation: _check_acl_path, _check_roles, kind/target checks) ...

    # ONE SAFE READ: current ACL state (fail-closed — None signals the read failed).
    acl_entries: list[dict] | None
    acl_error: str | None = None
    try:
        acl_entries = access_acl_list(api) or []
    except Exception as e:
        acl_entries = None
        acl_error = type(e).__name__

    result = blast.compute_acl_blast(path, roles, target, kind, delete, acl_entries, acl_error)

    return Plan(
        action="pve_acl_modify",
        target=f"acl:{path}:{target}",
        change=(
            f"{'revoke' if delete else 'grant'} role(s) {roles!r} {'from' if delete else 'to'} "
            f"{target!r} at path {path!r} (propagate={propagate})"
        ),
        current=result.current,
        blast_radius=result.summary_lines,
        affected=result.affected,
        risk=result.risk,
        risk_reasons=result.risk_reasons,
    )
```

- [ ] **Step 3: Run the existing ACL tests — they must pass unchanged (regression net)**

Run: `uv run python -m pytest tests/test_access.py -q`
Expected: PASS (all ~90, incl. the ~30 `plan_acl_modify` tests). If any shadow/widen/group-uncertainty test fails, the extraction changed behavior — fix the move, don't edit the test.

- [ ] **Step 4: Run full suite + ruff**

Run: `uv run python -m pytest -q && uv run ruff check src/proximo/blast.py src/proximo/access.py`
Expected: 2156+ green; ruff clean. (No import cycle: `access` imports `blast`; `blast` imports `cluster_ops`/`config_edit`/`planning` — none import `access`.)

- [ ] **Step 5: Commit**

```bash
git add src/proximo/blast.py src/proximo/access.py
git commit -m "refactor(acl): extract plan_acl_modify shadow/widen into pure blast.compute_acl_blast"
```

---

### Task 2: Populate structured `affected` with the target's role deltas

**Files:**
- Modify: `src/proximo/blast.py` (`compute_acl_blast`)
- Test: `tests/test_blast_acl.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_blast_acl.py`:

```python
"""ACL blast-radius engine — pure unit tests (zero API)."""

from __future__ import annotations

from proximo.blast import compute_acl_blast


def test_grant_shadow_populates_affected_loses():
    # target inherits Administrator at '/'; a new direct grant at /vms/100 shadows it.
    acl = [{"path": "/", "ugid": "bob@pam", "roleid": "Administrator", "type": "user", "propagate": True}]
    r = compute_acl_blast("/vms/100", "PVEVMUser", "bob@pam", "user", delete=False,
                          acl_entries=acl, acl_error=None)
    loses = [a for a in r.affected if a["change"] == "loses"]
    assert loses and loses[0]["principal"] == "bob@pam"
    assert "Administrator" in loses[0]["roles"]
    assert loses[0]["at"] == "/vms/100" and loses[0]["severity"] == "high"


def test_grant_widen_populates_affected_gains():
    r = compute_acl_blast("/vms/100", "PVEVMUser", "bob@pam", "user", delete=False,
                          acl_entries=[], acl_error=None)
    gains = [a for a in r.affected if a["change"] == "gains"]
    assert gains and gains[0]["principal"] == "bob@pam" and "PVEVMUser" in gains[0]["roles"]


def test_read_failure_affected_empty_but_high():
    r = compute_acl_blast("/vms/100", "PVEVMUser", "bob@pam", "user", delete=False,
                          acl_entries=None, acl_error="RuntimeError")
    assert r.risk == "high" and r.affected == []
    assert any("could NOT read" in line for line in r.summary_lines)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run python -m pytest tests/test_blast_acl.py -q`
Expected: FAIL — `r.affected` is empty (deltas not populated yet).

- [ ] **Step 3: Populate `affected` in `compute_acl_blast`**

In `compute_acl_blast`, build the affected list from the deltas. Insert just before the `return AclBlastResult(...)`:

```python
    affected: list[dict] = []
    sev = RISK_HIGH if risk == RISK_HIGH else RISK_MEDIUM
    if check_error is None:
        if shadowed_inherited:
            affected.append({
                "principal": target, "kind": kind,
                "via": "inherited (shadowed by the new direct entry)",
                "change": "loses", "roles": sorted(shadowed_inherited),
                "at": path, "severity": "high",
            })
        if widened:
            affected.append({
                "principal": target, "kind": kind, "via": "direct",
                "change": "gains", "roles": sorted(widened), "at": path, "severity": sev,
            })
```

Then change the return to pass `affected=affected`:

```python
    return AclBlastResult(summary_lines=blast, risk=risk, risk_reasons=reasons,
                          current=current, affected=affected)
```

- [ ] **Step 4: Run to verify pass + existing tests**

Run: `uv run python -m pytest tests/test_blast_acl.py tests/test_access.py -q`
Expected: PASS (new + existing).

- [ ] **Step 5: Commit**

```bash
git add src/proximo/blast.py tests/test_blast_acl.py
git commit -m "feat(acl): populate structured affected with target shadow/widen role deltas"
```

---

### Task 3: #1 — complete the target's shadow via group-inherited grants

**Files:**
- Modify: `src/proximo/blast.py` (`compute_acl_blast` gains a `target_groups` param)
- Modify: `src/proximo/access.py` (`plan_acl_modify` reads `user_get(target).groups`)
- Modify: `tests/test_blast_acl.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_blast_acl.py`:

```python
def test_group_inherited_role_is_folded_into_shadow():
    # bob is in group 'ops'; group ops has PVEVMAdmin at '/' (propagated). A new direct grant at
    # /vms/100 shadows the group-inherited role too. target_groups resolves the membership.
    acl = [{"path": "/", "ugid": "ops", "roleid": "PVEVMAdmin", "type": "group", "propagate": True}]
    r = compute_acl_blast("/vms/100", "PVEVMUser", "bob@pam", "user", delete=False,
                          acl_entries=acl, acl_error=None, target_groups=["ops"])
    loses = [a for a in r.affected if a["change"] == "loses"]
    assert any("PVEVMAdmin" in a["roles"] for a in loses)
    assert any("group ops" in a["via"] for a in loses)
    # resolution succeeded -> the generic "may be incomplete for group members" caveat is dropped
    assert not any("may be INCOMPLETE for users who are group members" in line for line in r.summary_lines)


def test_group_resolution_unavailable_retains_caveat():
    acl = [{"path": "/", "ugid": "ops", "roleid": "PVEVMAdmin", "type": "group", "propagate": True}]
    r = compute_acl_blast("/vms/100", "PVEVMUser", "bob@pam", "user", delete=False,
                          acl_entries=acl, acl_error=None, target_groups=None)  # user_get failed
    assert r.complete is False
    assert any("may be INCOMPLETE" in line for line in r.summary_lines)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run python -m pytest tests/test_blast_acl.py::test_group_inherited_role_is_folded_into_shadow tests/test_blast_acl.py::test_group_resolution_unavailable_retains_caveat -q`
Expected: FAIL — `compute_acl_blast` has no `target_groups` param.

- [ ] **Step 3: Add `target_groups` fold-in to `compute_acl_blast`**

Add the param (default `None` = not resolved): change the signature to add `target_groups: list[str] | None = None,` after `acl_error`. After the `inherited_entries` loop that matches `ugid == target`, ALSO match the target's groups and track which group each inherited role came from:

```python
    # #1: fold in roles the target inherits VIA THEIR OWN GROUP MEMBERSHIPS (ancestor, propagated).
    # target_groups None => resolution unavailable (user_get failed / privsep token) -> stay incomplete.
    group_inherited: dict[str, str] = {}   # roleid -> group it came from (for naming)
    groups_resolved = target_groups is not None
    if check_error is None and groups_resolved:
        gset = set(target_groups or [])
        for entry in entries:
            if entry.get("type") != "group" or entry.get("ugid", "") not in gset:
                continue
            ep = entry.get("path", "")
            if path.startswith(ep.rstrip("/") + "/") and entry.get("propagate", True):
                group_inherited[entry.get("roleid", "")] = entry.get("ugid", "")
        inherited_roles |= set(group_inherited)
        # recompute the shadow with the now-complete inherited set
        if not has_direct and not delete:
            shadowed_inherited = inherited_roles - new_roles
        if not has_direct:
            effective_before = inherited_roles
            widened = effective_after - effective_before
```

Make the group-uncertainty caveat conditional on resolution, and set `complete`. Replace the `if group_entries_present:` block's caveat emission so it only fires when groups are NOT resolved:

```python
        group_entries_present = any(
            e.get("type") == "group" and (
                e.get("path") == path or path.startswith(e.get("path", "").rstrip("/") + "/")
            )
            for e in entries
        )
        complete = True
        if group_entries_present and not groups_resolved:
            complete = False
            blast.append(
                "UNCERTAINTY: group-type ACL entries exist at or above this path and group "
                "membership could not be resolved — shadow/widen analysis may be INCOMPLETE for "
                "users who are group members"
            )
            reasons.append(
                "group-based ACL grants exist and were not resolved; shadow analysis may miss group-inherited privileges"
            )
```

When building the shadow `affected` entry (Task 2's `shadowed_inherited` block), name the group for group-inherited roles:

```python
        if shadowed_inherited:
            for role in sorted(shadowed_inherited):
                grp = group_inherited.get(role)
                via = f"inherited via group {grp}" if grp else "inherited (shadowed by the new direct entry)"
                affected.append({
                    "principal": target, "kind": kind, "via": via,
                    "change": "loses", "roles": [role], "at": path, "severity": "high",
                })
```

(Replace the single shadow `affected.append` from Task 2 with this per-role loop.) Initialize `complete = True` near the top of the success branch and thread it into the return: `return AclBlastResult(..., affected=affected, complete=complete)`. For the read-failure branch, set `complete = False`.

- [ ] **Step 4: Update `plan_acl_modify` to read the target's groups**

In `src/proximo/access.py`, after the acl_list read, resolve the target's groups (fail-closed → None) and pass them. Import `user_get` from `.access_users`.

```python
    # #1: resolve the target's OWN group memberships so the shadow analysis is complete.
    # kind=user: read the user's groups. kind=token: handled in Task 5 (privsep). None => unresolved.
    target_groups: list[str] | None = None
    if acl_entries is not None and kind == "user":
        try:
            target_groups = list(user_get(api, target).get("groups") or [])
        except Exception:
            target_groups = None

    result = blast.compute_acl_blast(path, roles, target, kind, delete,
                                     acl_entries, acl_error, target_groups=target_groups)
```

- [ ] **Step 5: Run new + existing tests**

Run: `uv run python -m pytest tests/test_blast_acl.py tests/test_access.py -q`
Expected: new PASS. **Existing group-uncertainty tests may now fail** (the caveat is now conditional on `groups_resolved`): with the `_acl_api` fake, `user_get` returns `{}` → `target_groups` could be `[]` (resolved-empty) rather than None — meaning the caveat is DROPPED. That is correct new behavior. Update `test_plan_acl_modify_group_entry_at_path_triggers_uncertainty_warning` and `..._at_ancestor_...` in `tests/test_access.py`: they now exercise the who-else path (Task 4), not the uncertainty caveat. Mark them xfail-with-reason OR move their assertions to Task 4's seam tests. For THIS task, update them to assert the caveat is GONE when groups resolve empty:

```python
def test_plan_acl_modify_group_entry_at_path_groups_resolved_no_incomplete_caveat():
    # _acl_api returns [] for /access/users/{t} -> target_groups resolves to [] (resolved, empty)
    # -> the generic "may be incomplete" caveat is NOT emitted.
    entries = [{"path": "/vms/100", "ugid": "ops", "roleid": "PVEVMAdmin", "type": "group", "propagate": True}]
    plan = plan_acl_modify(_acl_api(entries), "/vms/100", "PVEVMUser", "alice@pam", kind="user")
    assert not any("may be INCOMPLETE" in line for line in plan.blast_radius)
```

(Rename/replace the two old group-uncertainty tests with the resolved-behavior version above and its ancestor variant.)

- [ ] **Step 6: Run full suite + commit**

Run: `uv run python -m pytest -q`
Expected: green.

```bash
git add src/proximo/blast.py src/proximo/access.py tests/test_blast_acl.py tests/test_access.py
git commit -m "feat(acl): #1 complete target shadow via group-inherited grants; caveat now conditional on resolution"
```

---

### Task 4: #2 — who-else-can-reach context (UNCHANGED), via group members

**Files:**
- Modify: `src/proximo/blast.py` (`compute_acl_blast` gains a `group_members` param)
- Modify: `src/proximo/access.py` (`plan_acl_modify` reads `group_get(g).members`)
- Modify: `tests/test_blast_acl.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_blast_acl.py`:

```python
def test_who_else_members_are_unchanged_context():
    acl = [{"path": "/vms", "ugid": "ops", "roleid": "PVEVMAdmin", "type": "group", "propagate": True}]
    r = compute_acl_blast("/vms/100", "PVEVMUser", "bob@pam", "user", delete=False,
                          acl_entries=acl, acl_error=None, target_groups=[],
                          group_members={"ops": ["carol@pam", "dave@pam"]})
    who_else = [a for a in r.affected if a["change"] == "unchanged"]
    assert {a["principal"] for a in who_else} == {"carol@pam", "dave@pam"}
    assert all(a["kind"] == "group-member" and "group ops" in a["via"] for a in who_else)
    # honesty: who-else members are NEVER gains/loses
    assert all(a["change"] == "unchanged" for a in who_else)
    assert any("UNCHANGED" in line for line in r.summary_lines)


def test_who_else_unenumerable_group_is_disclosed_not_silent():
    acl = [{"path": "/vms", "ugid": "ops", "roleid": "PVEVMAdmin", "type": "group", "propagate": True}]
    r = compute_acl_blast("/vms/100", "PVEVMUser", "bob@pam", "user", delete=False,
                          acl_entries=acl, acl_error=None, target_groups=[],
                          group_members={"ops": None})  # group_get failed for ops
    assert r.complete is False
    assert any("could not enumerate members of group 'ops'" in line for line in r.summary_lines)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run python -m pytest tests/test_blast_acl.py -q -k who_else`
Expected: FAIL — no `group_members` param.

- [ ] **Step 3: Add `group_members` who-else assembly to `compute_acl_blast`**

Add param `group_members: dict[str, list[str] | None] | None = None,` to the signature (after `target_groups`). After the shadow/widen `affected` is built, append the who-else context. `group_members` maps each in-scope group → its members, or `None` if that group's read failed:

```python
    # #2: who-ELSE can reach this path (members of group-type ACL entries at/above). CONTEXT only —
    # their access is UNCHANGED by editing the target's entry (per-principal model). NEVER gains/loses.
    if check_error is None and group_members:
        named_any = False
        for grp, members in group_members.items():
            if members is None:
                complete = False
                blast.append(
                    f"could not enumerate members of group {grp!r} — "
                    "who-else-can-reach is INCOMPLETE (not a safety signal)"
                )
                continue
            for m in members:
                affected.append({
                    "principal": m, "kind": "group-member", "via": f"group {grp}",
                    "change": "unchanged", "roles": [], "at": path, "severity": "medium",
                })
                named_any = True
        if named_any:
            names = ", ".join(a["principal"] for a in affected if a["change"] == "unchanged")
            blast.append(
                f"also has access at this path — UNCHANGED by this change: {names} "
                "(via group membership; their access is computed independently of the target's entry)"
            )
```

- [ ] **Step 4: Update `plan_acl_modify` to read group members for in-scope groups**

In `src/proximo/access.py`, after resolving `target_groups`, enumerate the group-type ACL entries at/above the path and read each group's members (fail-closed per group → None). Import `group_get` from `.access_users`.

```python
    # #2: members of group-type ACL entries at/above the path (who-else-can-reach context).
    group_members: dict[str, list | None] = {}
    if acl_entries is not None:
        in_scope_groups = {
            e.get("ugid", "") for e in acl_entries
            if e.get("type") == "group" and (
                e.get("path") == path or path.startswith(e.get("path", "").rstrip("/") + "/")
            )
        }
        for grp in sorted(g for g in in_scope_groups if g):
            try:
                group_members[grp] = list(group_get(api, grp).get("members") or [])
            except Exception:
                group_members[grp] = None

    result = blast.compute_acl_blast(path, roles, target, kind, delete, acl_entries, acl_error,
                                     target_groups=target_groups, group_members=group_members or None)
```

- [ ] **Step 5: Run new + existing + full suite**

Run: `uv run python -m pytest tests/test_blast_acl.py tests/test_access.py -q && uv run python -m pytest -q`
Expected: green. (The Task 3 `_acl_api` group test now also produces who-else lines — adjust that test's assertions if it checks blast length; it should still pass the "no incomplete caveat" assertion.)

- [ ] **Step 6: Commit**

```bash
git add src/proximo/blast.py src/proximo/access.py tests/test_blast_acl.py tests/test_access.py
git commit -m "feat(acl): #2 who-else-can-reach members as UNCHANGED context (never gains/loses)"
```

---

### Task 5: privsep token handling

**Files:**
- Modify: `src/proximo/access.py` (`plan_acl_modify` token branch)
- Modify: `tests/test_blast_acl.py` (engine disclosure) + `tests/test_access.py` (seam)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_blast_acl.py`:

```python
def test_privsep1_token_target_groups_none_keeps_caveat():
    # A privsep=1 token does NOT inherit owner groups -> plan passes target_groups=None for it,
    # so when group entries are in scope the analysis stays honest (incomplete / not folded).
    acl = [{"path": "/", "ugid": "ops", "roleid": "PVEVMAdmin", "type": "group", "propagate": True}]
    r = compute_acl_blast("/vms/100", "PVEVMUser", "svc@pam!ci", "token", delete=False,
                          acl_entries=acl, acl_error=None, target_groups=None)
    assert r.complete is False
    assert any("may be INCOMPLETE" in line for line in r.summary_lines)
```

- [ ] **Step 2: Run to verify it passes for the engine (no engine change needed) — then add the plan branch test**

Run: `uv run python -m pytest tests/test_blast_acl.py::test_privsep1_token_target_groups_none_keeps_caveat -q`
Expected: PASS (engine already treats `target_groups=None` as unresolved from Task 3). The behavior under test is in `plan_acl_modify`'s token branch — add the seam assertion in Step 4.

- [ ] **Step 3: Add the privsep branch to `plan_acl_modify` in `src/proximo/access.py`**

Replace the Task 3 `target_groups` resolution with a kind-aware version. For `kind=token`, read the token's privsep via `access_tokens_list(owner)`; fold owner groups only when privsep is 0:

```python
    target_groups: list[str] | None = None
    if acl_entries is not None:
        if kind == "user":
            try:
                target_groups = list(user_get(api, target).get("groups") or [])
            except Exception:
                target_groups = None
        else:  # token: "owner@realm!tokenid" — inherits owner groups ONLY if privsep == 0
            owner = target.split("!", 1)[0]
            try:
                tid = target.split("!", 1)[1]
                tok = next((t for t in access_tokens_list(api, owner) if t.get("tokenid") == tid), None)
                privsep = tok.get("privsep", 1) if tok else 1   # default privsep=1 (least inheritance)
                if str(privsep) in ("0", "False"):
                    target_groups = list(user_get(api, owner).get("groups") or [])
                else:
                    target_groups = None  # privsep token: no owner-group inheritance -> stay honest
            except Exception:
                target_groups = None
```

- [ ] **Step 4: Add the seam test in `tests/test_access.py`**

Append a path-aware fake + test (the existing `_acl_api` only answers `/access/acl`):

```python
def _acl_api_full(acl_entries, *, groups=None, members=None, tokens=None):
    """Path-aware fake: /access/acl, /access/users/{id}, /access/groups/{id}, /access/users/{id}/token."""
    def fake_get(path):
        if path == "/access/acl":
            return list(acl_entries)
        if path.endswith("/token"):
            return list(tokens or [])
        if path.startswith("/access/users/"):
            return {"groups": list(groups or [])}
        if path.startswith("/access/groups/"):
            grp = path.rsplit("/", 1)[1]
            return {"members": list((members or {}).get(grp, []))}
        return []
    return SimpleNamespace(config=SimpleNamespace(node="pve"), _get=fake_get)


def test_plan_acl_modify_privsep1_token_does_not_fold_owner_groups():
    acl = [{"path": "/", "ugid": "ops", "roleid": "PVEVMAdmin", "type": "group", "propagate": True}]
    api = _acl_api_full(acl, tokens=[{"tokenid": "ci", "privsep": 1}])
    plan = plan_acl_modify(api, "/vms/100", "PVEVMUser", "svc@pam!ci", kind="token")
    assert any("may be INCOMPLETE" in line for line in plan.blast_radius)  # not folded -> honest
```

- [ ] **Step 5: Run + commit**

Run: `uv run python -m pytest tests/test_blast_acl.py tests/test_access.py -q && uv run python -m pytest -q`
Expected: green.

```bash
git add src/proximo/access.py tests/test_blast_acl.py tests/test_access.py
git commit -m "feat(acl): privsep-aware token group resolution (privsep=1 does not fold owner groups)"
```

---

### Task 6: Seam test — affected flows through the tool + ledger

**Files:**
- Test: `tests/test_blast_seam.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_blast_seam.py` (reuses its `_wire`/`_entries`):

```python
class _AclApi:
    def __init__(self, acl, groups=None, members=None):
        self.config = SimpleNamespace(node="pve1")
        self._acl, self._groups, self._members = acl, groups or [], members or {}

    def _get(self, path):
        if path == "/access/acl":
            return list(self._acl)
        if path.startswith("/access/users/") and path.endswith("/token"):
            return []
        if path.startswith("/access/users/"):
            return {"groups": list(self._groups)}
        if path.startswith("/access/groups/"):
            return {"members": list(self._members.get(path.rsplit("/", 1)[1], []))}
        return []

    def _put(self, path, data=None):
        return None


def test_acl_modify_plan_affected_in_response_and_ledger(tmp_path, monkeypatch):
    acl = [{"path": "/", "ugid": "bob@pam", "roleid": "Administrator", "type": "user", "propagate": True}]
    log = _wire(tmp_path, monkeypatch, _AclApi(acl, groups=[]))
    resp = server.pve_acl_modify("/vms/100", "PVEVMUser", "bob@pam", kind="user")  # dry-run
    assert resp["status"] == "plan" and resp["risk"] == "high"
    assert any(a["change"] == "loses" and "Administrator" in a["roles"] for a in resp["affected"])
    planned = [e for e in _entries(log) if e.get("outcome") == "planned"]
    assert planned and "affected" in planned[-1]["detail"]
```

- [ ] **Step 2: Run to verify it fails, then passes**

Run: `uv run python -m pytest tests/test_blast_seam.py::test_acl_modify_plan_affected_in_response_and_ledger -q`
Expected: PASS (the seam already records `affected`; this proves the ACL path end-to-end). If `pve_acl_modify`'s signature differs, check `server.py:1069` — params are `(path, roles, target, kind, propagate, delete, confirm)`.

- [ ] **Step 3: Commit**

```bash
git add tests/test_blast_seam.py
git commit -m "test(acl): seam — acl_modify plan surfaces affected via MCP response + PROVE ledger"
```

---

### Task 7: Gate + CHANGELOG + live-smoke + redteam

**Files:**
- Modify: `CHANGELOG.md`
- Create: `scripts/live-smoke/acl-blast-smoke.py`

- [ ] **Step 1: Lint + types + full suite**

Run: `uv run ruff check src tests && uv run pyright && uv run python -m pytest -q`
Expected: ruff clean; pyright 0 errors; suite green. Fix any findings.

- [ ] **Step 2: CHANGELOG entry under `[Unreleased]`**

Add under the existing `## [Unreleased]` → `### Added` in `CHANGELOG.md`:

```markdown
- **Computed blast-radius (access/ACL class).** `pve_acl_modify` now extracts its shadow/widen
  reasoning into the pure `proximo.blast.compute_acl_blast`, populates the structured `affected`
  field, **completes** the target's shadow by resolving their own group-inherited grants (#1), and
  lists who-else-can-reach the path as explicit **UNCHANGED** context (#2). Honest per-principal
  model: only the target gains/loses; group members are never reported as gaining/losing.
  privsep=1 tokens do not fold owner groups. Fail-closed throughout. (Spec:
  `docs/specs/2026-06-15-acl-blast-radius.md`.)
```

- [ ] **Step 3: Read-only live-smoke**

Create `scripts/live-smoke/acl-blast-smoke.py`:

```python
#!/usr/bin/env python3
"""Read-only ACL blast-radius smoke: PLAN an ACL grant against a live PVE and print the computed
impact. NEVER mutates (no confirm). Env: PROXIMO_* (see scripts/live-smoke/README.md).
Usage: PROXIMO_ACL_PATH=/vms PROXIMO_ACL_TARGET=user@pam PROXIMO_ACL_ROLES=PVEVMUser \\
       uv run python scripts/live-smoke/acl-blast-smoke.py"""
import json
import os
import sys

from proximo.access import plan_acl_modify
from proximo.server import _svc


def main() -> int:
    path = os.environ.get("PROXIMO_ACL_PATH")
    target = os.environ.get("PROXIMO_ACL_TARGET")
    roles = os.environ.get("PROXIMO_ACL_ROLES", "PVEVMUser")
    if not path or not target:
        print("set PROXIMO_ACL_PATH and PROXIMO_ACL_TARGET (read-only PLAN; no mutation)", file=sys.stderr)
        return 2
    _, api, _, _ = _svc()
    plan = plan_acl_modify(api, path, roles, target, kind="user")  # PLAN only — never confirm
    print(f"acl {roles} -> {target} at {path}: risk={plan.risk}")
    for line in plan.blast_radius:
        print(f"  {line}")
    print(json.dumps(plan.affected, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md scripts/live-smoke/acl-blast-smoke.py
git commit -m "docs+smoke(acl): CHANGELOG [Unreleased] + read-only ACL blast-radius live-smoke"
```

- [ ] **Step 5: Adversarial redteam (independent 3-lens, before "done")**

Dispatch independent review over the `feat/acl-blast-radius` diff:
- **correctness/under-flag:** can the shadow ever be under-computed (a real inherited role missed)? Does the group fold-in correctly recompute `shadowed_inherited`/`widened`? Path-prefix matching edge cases (`/vms` vs `/vms2`)?
- **honesty/false-gains-loses:** can a who-else member EVER carry `gains`/`loses`? Is the "incomplete" caveat ever dropped when a read actually failed? Does any read swallow into a clean result? privsep default safe (defaults to no-fold)?
- **leak:** generic fixtures only (`bob@pam`, `ops`, `/vms/100`) — no real principals/realms.

Apply confirmed findings test-first; re-run Step 1's gate. Then run the read-only `acl-blast-smoke.py` on x3650 (GREEN-zone read) to prove end-to-end.

---

## Self-Review (run after writing — checklist, not a subagent)

**Spec coverage:**
- Pure `compute_acl_blast` extraction → Task 1 ✅
- Structured `affected` (target deltas) → Task 2 ✅
- #1 group-inherited shadow completion + conditional caveat → Task 3 ✅
- #2 who-else as UNCHANGED context + per-group fail-closed → Task 4 ✅
- privsep=1 token does not fold owner groups → Task 5 ✅
- Per-principal honesty (gains/loses only for target) → Tasks 2/4 assertions ✅
- Fail-closed reads (acl_list / user_get / group_get) → Tasks 1/3/4 ✅
- `affected` via MCP response + ledger (MCP-only, not A2A) → Task 6 ✅
- Existing behavior preserved → Task 1 regression net ✅
- Gate + CHANGELOG + live-smoke + redteam → Task 7 ✅

**Placeholder scan:** No TBD/TODO; every code step shows complete code or a precise verbatim-move instruction (Task 1) for existing logic the engineer has in-file. ✅

**Type consistency:** `compute_acl_blast(path, roles, target, kind, delete, acl_entries, acl_error, target_groups, group_members)` and `AclBlastResult(summary_lines, risk, risk_reasons, current, affected, complete)` are consistent across Tasks 1-6. `affected` entry keys (`principal/kind/via/change/roles/at/severity`) match the spec and all tests. ✅
