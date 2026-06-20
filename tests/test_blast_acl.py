"""ACL blast-radius engine — pure unit tests (zero API).

Per-principal honesty constraint asserted directly: only the TARGET gains/loses; who-else members
are 'unchanged' context, never gains/loses; reads fail closed (caveat retained, never 'safe').
"""

from __future__ import annotations

from proximo.blast import RISK_HIGH, compute_acl_blast


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


def test_group_inherited_role_is_folded_into_shadow():
    # bob is in group 'ops'; group ops has PVEVMAdmin at '/' (propagated). A new direct grant at
    # /vms/100 shadows it. target_groups resolves the membership -> shadow now names the group role.
    acl = [{"path": "/", "ugid": "ops", "roleid": "PVEVMAdmin", "type": "group", "propagate": True}]
    r = compute_acl_blast("/vms/100", "PVEVMUser", "bob@pam", "user", delete=False,
                          acl_entries=acl, acl_error=None, target_groups=["ops"])
    loses = [a for a in r.affected if a["change"] == "loses"]
    assert any("PVEVMAdmin" in a["roles"] for a in loses)
    assert any("group ops" in a["via"] for a in loses)
    assert r.complete is True
    assert not any("may be INCOMPLETE" in line for line in r.summary_lines)


def test_group_resolution_unavailable_retains_caveat():
    acl = [{"path": "/", "ugid": "ops", "roleid": "PVEVMAdmin", "type": "group", "propagate": True}]
    r = compute_acl_blast("/vms/100", "PVEVMUser", "bob@pam", "user", delete=False,
                          acl_entries=acl, acl_error=None, target_groups=None)  # user_get failed
    assert r.complete is False
    assert any("may be INCOMPLETE" in line for line in r.summary_lines)


def test_unresolved_groups_forces_high_risk():
    # Honesty contract: incomplete enumeration that could HIDE a widen (a group entry exists in
    # scope but the target's membership couldn't be resolved) forces risk UP — a disclosure line
    # alone under-reports via the structured risk field. Over-flag is acceptable; under-flag is the sin.
    acl = [{"path": "/", "ugid": "ops", "roleid": "PVEVMAdmin", "type": "group", "propagate": True}]
    r = compute_acl_blast("/vms/100", "PVEVMUser", "bob@pam", "user", delete=True,
                          acl_entries=acl, acl_error=None, target_groups=None)  # user_get failed
    assert r.complete is False
    assert r.risk == RISK_HIGH


def test_who_else_members_are_unchanged_context():
    acl = [{"path": "/vms", "ugid": "ops", "roleid": "PVEVMAdmin", "type": "group", "propagate": True}]
    r = compute_acl_blast("/vms/100", "PVEVMUser", "bob@pam", "user", delete=False,
                          acl_entries=acl, acl_error=None, target_groups=[],
                          group_members={"ops": ["carol@pam", "dave@pam"]})
    who_else = [a for a in r.affected if a["change"] == "unchanged"]
    assert {a["principal"] for a in who_else} == {"carol@pam", "dave@pam"}
    assert all(a["kind"] == "group-member" and "group ops" in a["via"] for a in who_else)
    # honesty: who-else members are NEVER gains/loses
    assert not any(a["change"] in ("gains", "loses") and a["kind"] == "group-member" for a in r.affected)
    assert any("UNCHANGED" in line for line in r.summary_lines)


def test_who_else_unenumerable_group_is_disclosed_not_silent():
    acl = [{"path": "/vms", "ugid": "ops", "roleid": "PVEVMAdmin", "type": "group", "propagate": True}]
    r = compute_acl_blast("/vms/100", "PVEVMUser", "bob@pam", "user", delete=False,
                          acl_entries=acl, acl_error=None, target_groups=[],
                          group_members={"ops": None})  # group_get failed for ops
    assert r.complete is False
    assert any("could not enumerate members of group 'ops'" in line for line in r.summary_lines)


def test_privsep1_token_target_groups_none_keeps_caveat():
    # A privsep=1 token does NOT inherit owner groups -> plan passes target_groups=None,
    # so a group entry in scope keeps the analysis honest (incomplete, not silently folded).
    acl = [{"path": "/", "ugid": "ops", "roleid": "PVEVMAdmin", "type": "group", "propagate": True}]
    r = compute_acl_blast("/vms/100", "PVEVMUser", "svc@pam!ci", "token", delete=False,
                          acl_entries=acl, acl_error=None, target_groups=None)
    assert r.complete is False
    assert any("may be INCOMPLETE" in line for line in r.summary_lines)


def test_privsep0_token_folds_owner_direct_ancestor_grant_into_shadow():
    # CRITICAL regression: a privsep=0 token IS the owner. Owner has a DIRECT user grant
    # (Administrator at /, propagated) — not a group grant. The token inherits it; a new direct
    # entry for the token at /vms/100 shadows it. extra_inherited carries owner's direct grants.
    acl = [{"path": "/", "ugid": "svc@pam", "roleid": "Administrator", "type": "user", "propagate": True}]
    r = compute_acl_blast("/vms/100", "PVEVMUser", "svc@pam!ci", "token", delete=False,
                          acl_entries=acl, acl_error=None, target_groups=[],
                          extra_inherited={"Administrator": "token owner svc@pam (direct)"})
    loses = [a for a in r.affected if a["change"] == "loses"]
    assert any("Administrator" in a["roles"] for a in loses)
    assert r.risk == "high"


def test_compute_acl_none_entries_without_error_is_still_high_fail_closed():
    # HIGH (latent): acl_entries=None means the read FAILED regardless of whether acl_error was
    # passed. Must NOT fall through to a clean MEDIUM "additive" plan.
    r = compute_acl_blast("/vms/100", "PVEVMUser", "bob@pam", "user", delete=False,
                          acl_entries=None, acl_error=None)
    assert r.risk == "high" and r.complete is False
    assert any("could NOT read" in line for line in r.summary_lines)
