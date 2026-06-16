"""Guest-destroy blast-radius engine — pure unit tests (zero API)."""
from __future__ import annotations

from proximo.blast import (
    _GUEST_DESTROY_DISCLAIMER,
    GuestDestroyBlastResult,
    GuestDestroyInputs,
    _is_linked_clone_of,
    compute_guest_destroy_blast,
    gather_guest_dependents,
    guest_destroy_blast,
)
from proximo.planning import RISK_HIGH


def _inputs(**over) -> GuestDestroyInputs:
    """A minimal all-reads-succeeded, nothing-found input. Override per test."""
    base = dict(
        vmid="9000", kind="qemu", purge=False, force=False,
        guest_config={}, status="stopped",
        ha_resources=[], replication_jobs=[], backup_jobs=[],
        pools=[], snapshots=[], clone_configs={},
    )
    base.update(over)
    return GuestDestroyInputs(**base)


def test_dataclasses_exist_and_disclaimer_mentions_plan_time():
    inp = _inputs()
    assert inp.vmid == "9000"
    assert "PLAN time" in _GUEST_DESTROY_DISCLAIMER or "plan time" in _GUEST_DESTROY_DISCLAIMER.lower()
    # result is constructible with the documented field set
    r = GuestDestroyBlastResult(
        summary_lines=["x"], affected=[], risk=RISK_HIGH, risk_reasons=[], complete=True,
    )
    assert r.risk == RISK_HIGH and r.complete is True


def test_informational_disks_snapshots_pool():
    inp = _inputs(
        vmid="9000", kind="qemu",
        guest_config={"scsi0": "local-lvm:vm-9000-disk-0,size=32G",
                      "scsi1": "nas:vm-9000-disk-1,size=100G"},
        snapshots=[{"name": "pre-upgrade"}, {"name": "current"}],
        pools=[{"poolid": "prod", "members": [{"vmid": 9000}]}],
    )
    r = compute_guest_destroy_blast(inp)
    assert r.risk == RISK_HIGH and r.complete is True
    kinds = {a["kind"] for a in r.affected}
    assert {"disk", "snapshots", "pool"} <= kinds
    disks = [a for a in r.affected if a["kind"] == "disk"]
    assert {d["ref"] for d in disks} == {"local-lvm", "nas"}  # storages named
    snap = next(a for a in r.affected if a["kind"] == "snapshots")
    # PVE's snapshot endpoint always includes a synthetic {"name": "current"} (the live state) —
    # it is NOT a real snapshot and must be excluded from the count. Two entries here, one is
    # "current", so the real count is 1.
    assert "1" in snap["effect"] and "2" not in snap["effect"]  # synthetic 'current' excluded
    pool = next(a for a in r.affected if a["kind"] == "pool")
    assert pool["ref"] == "prod"
    assert all(a["category"] == "informational" for a in r.affected)


def test_only_current_snapshot_emits_no_entry():
    # A guest with no real snapshots still has the synthetic {"name": "current"} entry — that
    # alone must NOT produce a snapshots affected entry (there is nothing to remove).
    r = compute_guest_destroy_blast(_inputs(snapshots=[{"name": "current"}]))
    assert not [a for a in r.affected if a["kind"] == "snapshots"]


def test_snapshot_read_failure_is_incomplete_not_zero():
    # None snapshots == read failed -> must NOT silently say "no snapshots"
    inp = _inputs(snapshots=None)
    r = compute_guest_destroy_blast(inp)
    assert r.complete is False
    assert any("snapshot" in s.lower() and "could not" in s.lower() for s in r.summary_lines)


def test_protection_refuses_regardless_of_force():
    for force in (False, True):
        inp = _inputs(guest_config={"protection": 1}, force=force)
        r = compute_guest_destroy_blast(inp)
        wp = [a for a in r.affected if a["kind"] == "protection"]
        assert wp, f"protection not flagged (force={force})"
        assert wp[0]["category"] == "wont_proceed"
        assert any("protection" in s.lower() for s in r.risk_reasons)
        # force must NOT be described as overriding protection
        assert "force" not in wp[0]["effect"].lower() or "not" in wp[0]["effect"].lower()


def test_running_without_force_refuses():
    inp = _inputs(status="running", force=False)
    r = compute_guest_destroy_blast(inp)
    wp = [a for a in r.affected if a["kind"] == "running"]
    assert wp and wp[0]["category"] == "wont_proceed"
    assert "force" in wp[0]["effect"].lower()  # names the override that's missing
    assert any("running" in s.lower() for s in r.risk_reasons)


def test_running_with_force_proceeds_not_a_refusal():
    inp = _inputs(status="running", force=True)
    r = compute_guest_destroy_blast(inp)
    # there must be NO wont_proceed/running entry — force overrides the running guard
    assert not [a for a in r.affected if a["kind"] == "running" and a["category"] == "wont_proceed"]


def test_stopped_guest_has_no_running_entry():
    r = compute_guest_destroy_blast(_inputs(status="stopped"))
    assert not [a for a in r.affected if a["kind"] == "running"]


def test_unknown_status_force_false_is_incomplete():
    # status="unknown" (the status re-read failed) with force=False must NOT silently produce a
    # clean complete=True "go" — if the guest is actually running, PVE will REFUSE. Flag it.
    r = compute_guest_destroy_blast(_inputs(status="unknown", force=False))
    assert r.complete is False
    assert any(
        "could not confirm run-state" in s.lower() for s in r.summary_lines
    )


def test_unknown_status_force_true_not_flagged():
    # force=True overrides the running guard, so an unknown status is irrelevant to the destroy
    # proceeding — this cause must NOT mark the result incomplete.
    r = compute_guest_destroy_blast(_inputs(status="unknown", force=True))
    assert not any("could not confirm run-state" in s.lower() for s in r.summary_lines)


def test_is_linked_clone_of_detects_base_backing():
    clone_cfg = {"scsi0": "local-lvm:base-9000-disk-0/vm-101-disk-0,size=32G"}
    assert _is_linked_clone_of(clone_cfg, "9000") is True
    # a full/independent disk does not reference the template base
    assert _is_linked_clone_of({"scsi0": "local-lvm:vm-101-disk-0,size=32G"}, "9000") is False
    # different template
    assert _is_linked_clone_of(clone_cfg, "8000") is False


def test_template_with_clones_refuses_and_names_them():
    inp = _inputs(
        vmid="9000", guest_config={"template": 1},
        clone_configs={
            "101": {"scsi0": "local-lvm:base-9000-disk-0/vm-101-disk-0"},
            "102": {"scsi0": "local-lvm:base-9000-disk-0/vm-102-disk-0"},
            "200": {"scsi0": "local-lvm:vm-200-disk-0"},  # not a clone
        },
        force=True,  # force must NOT clear this
    )
    r = compute_guest_destroy_blast(inp)
    wp = [a for a in r.affected if a["kind"] == "template_clones"]
    assert wp and wp[0]["category"] == "wont_proceed"
    assert "101" in wp[0]["ref"] and "102" in wp[0]["ref"] and "200" not in wp[0]["ref"]
    assert any("clone" in s.lower() for s in r.risk_reasons)


def test_template_emits_storage_backend_caveat():
    # A template with a READABLE clone scan (no config-visible clones found) must STILL carry a
    # caveat: config-based linked-clone detection cannot see directory/qcow2 backing chains.
    inp = _inputs(guest_config={"template": 1}, clone_configs={})
    r = compute_guest_destroy_blast(inp)
    assert any(
        "directory/qcow2" in s.lower() or "config-based" in s.lower() for s in r.summary_lines
    )
    # the caveat is a documented limitation, not a failed read — it must NOT lower completeness
    assert r.complete is True


def test_non_template_gets_no_storage_backend_caveat():
    inp = _inputs(guest_config={"scsi0": "local-lvm:vm-9000-disk-0,size=8G"})
    r = compute_guest_destroy_blast(inp)
    assert not any(
        "directory/qcow2" in s.lower() or "config-based" in s.lower() for s in r.summary_lines
    )


def test_template_clone_scan_unreadable_is_incomplete():
    inp = _inputs(guest_config={"template": 1}, clone_configs=None)
    r = compute_guest_destroy_blast(inp)
    assert r.complete is False
    assert any("clone" in s.lower() and "could not" in s.lower() for s in r.summary_lines)


def test_ha_reference_dangling_when_purge_false():
    inp = _inputs(vmid="9000", kind="qemu", purge=False,
                  ha_resources=[{"sid": "vm:9000", "state": "started"},
                                {"sid": "vm:7777", "state": "started"}])
    r = compute_guest_destroy_blast(inp)
    ha = [a for a in r.affected if a["kind"] == "ha"]
    assert len(ha) == 1 and ha[0]["ref"] == "vm:9000"
    assert ha[0]["category"] == "reference"
    assert "dangl" in ha[0]["effect"].lower()  # left dangling
    assert "remov" not in ha[0]["effect"].lower() or "manual" in ha[0]["effect"].lower()


def test_ha_reference_cleaned_when_purge_true():
    inp = _inputs(vmid="9000", kind="qemu", purge=True,
                  ha_resources=[{"sid": "vm:9000", "state": "started"}])
    r = compute_guest_destroy_blast(inp)
    ha = next(a for a in r.affected if a["kind"] == "ha")
    assert "remov" in ha["effect"].lower() or "clean" in ha["effect"].lower()
    assert "dangl" not in ha["effect"].lower()  # MUST NOT claim the opposite of what purge does


def test_ha_lxc_sid_matches_ct():
    inp = _inputs(vmid="200", kind="lxc", ha_resources=[{"sid": "ct:200"}])
    r = compute_guest_destroy_blast(inp)
    assert [a for a in r.affected if a["kind"] == "ha"]


def test_ha_read_failure_incomplete():
    r = compute_guest_destroy_blast(_inputs(ha_resources=None))
    assert r.complete is False
    assert any("ha" in s.lower() and "could not" in s.lower() for s in r.summary_lines)


def test_replication_job_matched_by_vmid_prefix():
    inp = _inputs(vmid="9000", purge=False,
                  replication_jobs=[{"id": "9000-0", "target": "node2"},
                                    {"id": "9000-1", "target": "node3"},
                                    {"id": "7777-0", "target": "node2"}])
    r = compute_guest_destroy_blast(inp)
    rep = [a for a in r.affected if a["kind"] == "replication"]
    assert {x["ref"] for x in rep} == {"9000-0", "9000-1"}
    assert all("dangl" in x["effect"].lower() for x in rep)


def test_replication_purge_true_cleaned():
    inp = _inputs(vmid="9000", purge=True, replication_jobs=[{"id": "9000-0"}])
    r = compute_guest_destroy_blast(inp)
    rep = next(a for a in r.affected if a["kind"] == "replication")
    assert "remov" in rep["effect"].lower() and "dangl" not in rep["effect"].lower()


def test_replication_id_prefix_is_exact_not_substring():
    # "90001-0" must NOT match vmid 9000
    inp = _inputs(vmid="9000", replication_jobs=[{"id": "90001-0"}])
    r = compute_guest_destroy_blast(inp)
    assert not [a for a in r.affected if a["kind"] == "replication"]


def test_replication_read_failure_incomplete():
    r = compute_guest_destroy_blast(_inputs(replication_jobs=None))
    assert r.complete is False


def test_backup_explicit_vmid_list_matched():
    inp = _inputs(vmid="9000", purge=False,
                  backup_jobs=[{"id": "job-A", "vmid": "9000,7777"},
                               {"id": "job-B", "vmid": "100,200"}])
    r = compute_guest_destroy_blast(inp)
    bk = [a for a in r.affected if a["kind"] == "backup_job"]
    assert [x["ref"] for x in bk] == ["job-A"]
    assert "dangl" in bk[0]["effect"].lower()
    assert r.complete is True  # explicit lists are fully resolvable


def test_backup_purge_true_cleaned():
    inp = _inputs(vmid="9000", purge=True, backup_jobs=[{"id": "job-A", "vmid": "9000"}])
    r = compute_guest_destroy_blast(inp)
    bk = next(a for a in r.affected if a["kind"] == "backup_job")
    assert "remov" in bk["effect"].lower() and "dangl" not in bk["effect"].lower()


# --- Updated: all mode is now RESOLVED, not incomplete (live-dogfood gap 2026-06-16) ---
# Prior test: "all mode → complete=False, no entry." New behavior: all=1 means the guest IS
# covered unless excluded — so a non-excluded guest gets a backup_job reference entry, complete=True.
def test_backup_all_mode_resolved_covered_when_not_excluded():
    # all=1, target NOT excluded → backup_job entry emitted, complete is True.
    inp = _inputs(vmid="9000", backup_jobs=[{"id": "job-all", "all": 1}])
    r = compute_guest_destroy_blast(inp)
    assert r.complete is True
    bk = [a for a in r.affected if a["kind"] == "backup_job" and a["ref"] == "job-all"]
    assert len(bk) == 1, "all=1 with non-excluded target must emit a backup_job reference"


# --- Updated: pool mode with readable pools is now resolved; only unreadable pools = incomplete. ---
# exclude-only (no all, no pool, no vmid) still falls into the unrecognizable branch → incomplete.
def test_backup_pool_unreadable_and_exclude_only_are_incomplete():
    # pool=X with pools=None (unreadable) → still incomplete (cannot resolve membership)
    r = compute_guest_destroy_blast(_inputs(vmid="9000", backup_jobs=[{"id": "j", "pool": "prod"}], pools=None))
    assert r.complete is False
    # exclude-only (no all/pool/vmid) → unrecognizable selection → incomplete
    r2 = compute_guest_destroy_blast(_inputs(vmid="9000", backup_jobs=[{"id": "j", "exclude": "100"}]))
    assert r2.complete is False


# --- New tests for the all/pool/explicit tri-state resolution ---

def test_backup_all_mode_covered_unless_excluded():
    # all=1, target 9000 NOT in exclude list → backup_job reference emitted, complete True
    job = {"id": "j", "all": 1, "exclude": "100,101"}
    r = compute_guest_destroy_blast(_inputs(vmid="9000", backup_jobs=[job]))
    bk = [a for a in r.affected if a["kind"] == "backup_job"]
    assert len(bk) == 1 and bk[0]["ref"] == "j"
    assert r.complete is True


def test_backup_all_mode_excluded_not_covered():
    # all=1, target 100 IS in exclude list → no entry, complete True (resolved, not incomplete)
    job = {"id": "j", "all": 1, "exclude": "100,101"}
    r = compute_guest_destroy_blast(_inputs(vmid="100", backup_jobs=[job]))
    bk = [a for a in r.affected if a["kind"] == "backup_job"]
    assert len(bk) == 0
    assert r.complete is True


def test_backup_pool_mode_covered_when_in_pool():
    # pool="prod", target 9000 is a member of pool "prod" → backup_job reference emitted
    job = {"id": "j", "pool": "prod"}
    pools = [{"poolid": "prod", "members": [{"vmid": 9000}]}]
    r = compute_guest_destroy_blast(_inputs(vmid="9000", backup_jobs=[job], pools=pools))
    bk = [a for a in r.affected if a["kind"] == "backup_job"]
    assert len(bk) == 1 and bk[0]["ref"] == "j"
    assert r.complete is True


def test_backup_pool_mode_not_covered_when_not_in_pool():
    # pool="prod", target 9000 is NOT a member (only 7777 is) → no entry, complete True
    job = {"id": "j", "pool": "prod"}
    pools = [{"poolid": "prod", "members": [{"vmid": 7777}]}]
    r = compute_guest_destroy_blast(_inputs(vmid="9000", backup_jobs=[job], pools=pools))
    bk = [a for a in r.affected if a["kind"] == "backup_job"]
    assert len(bk) == 0
    assert r.complete is True


def test_backup_pool_mode_incomplete_when_pools_unreadable():
    # pool="prod", but pools=None (read failed) → cannot resolve → complete False
    job = {"id": "j", "pool": "prod"}
    r = compute_guest_destroy_blast(_inputs(vmid="9000", backup_jobs=[job], pools=None))
    assert r.complete is False


def test_backup_all_mode_reference_is_purge_conditional():
    # all=1 covered, purge=False → "dangling"; purge=True → "remov", NOT "dangling"
    job = {"id": "j", "all": 1}
    r_no_purge = compute_guest_destroy_blast(_inputs(vmid="9000", purge=False, backup_jobs=[job]))
    bk_no_purge = next(a for a in r_no_purge.affected if a["kind"] == "backup_job")
    assert "dangl" in bk_no_purge["effect"].lower()

    r_purge = compute_guest_destroy_blast(_inputs(vmid="9000", purge=True, backup_jobs=[job]))
    bk_purge = next(a for a in r_purge.affected if a["kind"] == "backup_job")
    assert "remov" in bk_purge["effect"].lower()
    assert "dangl" not in bk_purge["effect"].lower()


def test_backup_unrecognizable_selection_incomplete():
    # all=0, no pool, no vmid → unrecognizable selection → complete False
    job = {"id": "j", "all": 0}
    r = compute_guest_destroy_blast(_inputs(vmid="9000", backup_jobs=[job]))
    assert r.complete is False


def test_backup_read_failure_incomplete():
    r = compute_guest_destroy_blast(_inputs(backup_jobs=None))
    assert r.complete is False


def test_backup_explicit_vmid_with_falsy_all_key_still_matched():
    # PVE may serialize all=0 on an explicit-vmid job; value-coercion (not key presence) must
    # still treat it as explicit and match the vmid.
    inp = _inputs(vmid="9000", purge=False,
                  backup_jobs=[{"id": "job-A", "vmid": "9000,7777", "all": 0, "pool": "", "exclude": ""}])
    r = compute_guest_destroy_blast(inp)
    bk = [a for a in r.affected if a["kind"] == "backup_job"]
    assert [x["ref"] for x in bk] == ["job-A"]
    assert r.complete is True


def test_guest_config_read_failure_is_incomplete():
    r = compute_guest_destroy_blast(_inputs(guest_config=None))
    assert r.complete is False
    assert any("config" in s.lower() and "could not" in s.lower() for s in r.summary_lines)


# ===========================================================================
# Task 9: I/O gather layer tests
# ===========================================================================

class _FakeApi:
    """Minimal stand-in: each attr is the value to return, or an Exception to raise."""
    def __init__(self, **kw):
        self._kw = kw
        class _C:  # api.config.node fallback
            node = "n1"
        self.config = _C()

    def _maybe(self, key, default):
        v = self._kw.get(key, default)
        if isinstance(v, Exception):
            raise v
        return v

    def _get(self, path):
        if path == "/cluster/replication":
            return self._maybe("replication", [])
        if path == "/cluster/backup":
            return self._maybe("backup", [])
        raise AssertionError(f"unexpected path {path}")

    def snapshot_list(self, vmid, kind="lxc", node=None):
        return self._maybe("snapshots", [])

    def guest_status(self, vmid, kind="lxc", node=None):
        return self._maybe("guest_status", {"status": "stopped"})


def test_gather_packs_inputs_and_is_fail_closed(monkeypatch):
    import proximo.blast as B
    monkeypatch.setattr(B, "cluster_resources",
                        lambda api: [{"vmid": 9000, "type": "qemu", "node": "n1", "pool": "prod"},
                                     {"vmid": 101, "type": "qemu", "node": "n1"}])
    monkeypatch.setattr(B, "guest_config_get",
                        lambda api, vmid, kind, node=None: {"template": 1} if str(vmid) == "9000"
                        else {"scsi0": "local-lvm:base-9000-disk-0/vm-101-disk-0"})
    monkeypatch.setattr(B, "ha_resources_list", lambda api: [{"sid": "vm:9000"}])
    monkeypatch.setattr(B, "pools_list", lambda api: [{"poolid": "prod", "members": [{"vmid": 9000}]}])
    api = _FakeApi(replication=[{"id": "9000-0"}], backup=[{"id": "j", "vmid": "9000"}],
                   snapshots=[{"name": "s1"}], guest_status={"status": "running"})
    inp = gather_guest_dependents(api, "9000", "qemu", "n1", purge=False, force=False)
    assert inp.guest_config == {"template": 1}
    assert inp.clone_configs and "101" in inp.clone_configs and "9000" not in inp.clone_configs
    assert inp.ha_resources == [{"sid": "vm:9000"}]
    assert inp.replication_jobs == [{"id": "9000-0"}]
    assert inp.status == "running"


def test_gather_read_failures_become_none(monkeypatch):
    import proximo.blast as B
    monkeypatch.setattr(B, "cluster_resources", lambda api: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(B, "guest_config_get",
                        lambda api, vmid, kind, node=None: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(B, "ha_resources_list", lambda api: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr(B, "pools_list", lambda api: (_ for _ in ()).throw(RuntimeError("x")))
    api = _FakeApi(replication=RuntimeError("x"), backup=RuntimeError("x"), snapshots=RuntimeError("x"))
    inp = gather_guest_dependents(api, "9000", "qemu", "n1", purge=False, force=False)
    assert inp.guest_config is None and inp.ha_resources is None
    assert inp.replication_jobs is None and inp.backup_jobs is None
    assert inp.pools is None and inp.snapshots is None and inp.clone_configs is None
    # the whole thing still computes (never raises) and is flagged incomplete
    r = guest_destroy_blast(api, "9000", "qemu", "n1", purge=False, force=False)
    assert r.complete is False and r.risk == RISK_HIGH


def test_gather_template_with_unreadable_peer_is_incomplete(monkeypatch):
    # Target is a TEMPLATE; one peer config read fails (it may be a linked clone we now can't see).
    # Silently dropping it would make compute find no clones -> false complete=True "go". Instead the
    # clone scan must report unknown: clone_configs=None -> compute flags incomplete.
    import proximo.blast as B
    monkeypatch.setattr(B, "cluster_resources",
                        lambda api: [{"vmid": 9000, "type": "qemu", "node": "n1"},
                                     {"vmid": 101, "type": "qemu", "node": "n1"},
                                     {"vmid": 102, "type": "qemu", "node": "n1"}])

    def _cfg(api, vmid, kind, node=None):
        if str(vmid) == "9000":
            return {"template": 1}
        if str(vmid) == "101":
            raise RuntimeError("peer config read failed")
        return {"scsi0": "local-lvm:vm-102-disk-0"}

    monkeypatch.setattr(B, "guest_config_get", _cfg)
    monkeypatch.setattr(B, "ha_resources_list", lambda api: [])
    monkeypatch.setattr(B, "pools_list", lambda api: [])
    api = _FakeApi(replication=[], backup=[], snapshots=[], guest_status={"status": "stopped"})
    inp = gather_guest_dependents(api, "9000", "qemu", "n1", purge=False, force=False)
    assert inp.clone_configs is None
    r = guest_destroy_blast(api, "9000", "qemu", "n1", purge=False, force=False)
    assert r.complete is False


def test_gather_template_all_peers_read_detects_clones_complete(monkeypatch):
    # Happy path: a template whose peers ALL read fine still detects the config-visible clone and
    # stays complete=True (the partial-scan fix must not regress the clean case).
    import proximo.blast as B
    monkeypatch.setattr(B, "cluster_resources",
                        lambda api: [{"vmid": 9000, "type": "qemu", "node": "n1"},
                                     {"vmid": 101, "type": "qemu", "node": "n1"}])
    monkeypatch.setattr(B, "guest_config_get",
                        lambda api, vmid, kind, node=None: {"template": 1} if str(vmid) == "9000"
                        else {"scsi0": "local-lvm:base-9000-disk-0/vm-101-disk-0"})
    monkeypatch.setattr(B, "ha_resources_list", lambda api: [])
    monkeypatch.setattr(B, "pools_list", lambda api: [])
    api = _FakeApi(replication=[], backup=[], snapshots=[], guest_status={"status": "stopped"})
    inp = gather_guest_dependents(api, "9000", "qemu", "n1", purge=False, force=False)
    assert inp.clone_configs and "101" in inp.clone_configs
    r = guest_destroy_blast(api, "9000", "qemu", "n1", purge=False, force=False)
    assert r.complete is True
    assert [a for a in r.affected if a["kind"] == "template_clones"]


def test_gather_non_template_skips_clone_scan(monkeypatch):
    # A non-template target does NOT need the peer-config clone scan (saves I/O). clone_configs is
    # an empty dict (the template branch in compute won't use it) and the result stays complete.
    import proximo.blast as B
    monkeypatch.setattr(B, "cluster_resources",
                        lambda api: [{"vmid": 9000, "type": "qemu", "node": "n1"},
                                     {"vmid": 101, "type": "qemu", "node": "n1"}])
    calls: list = []

    def _cfg(api, vmid, kind, node=None):
        calls.append(str(vmid))
        if str(vmid) == "9000":
            return {"scsi0": "local-lvm:vm-9000-disk-0"}  # not a template
        return {"scsi0": "local-lvm:vm-101-disk-0"}

    monkeypatch.setattr(B, "guest_config_get", _cfg)
    monkeypatch.setattr(B, "ha_resources_list", lambda api: [])
    monkeypatch.setattr(B, "pools_list", lambda api: [])
    api = _FakeApi(replication=[], backup=[], snapshots=[], guest_status={"status": "stopped"})
    inp = gather_guest_dependents(api, "9000", "qemu", "n1", purge=False, force=False)
    assert inp.clone_configs == {}            # no clones map needed for a non-template
    assert "101" not in calls                  # peer config NOT read (clone scan skipped)
    r = guest_destroy_blast(api, "9000", "qemu", "n1", purge=False, force=False)
    assert r.complete is True


def test_gather_resolves_pool_members_via_pool_get(monkeypatch):
    # pools_list returns only summaries (no members) — gather must resolve each pool's members via
    # pool_get(api, poolid) so compute can match the target to its pool.
    import proximo.blast as B
    monkeypatch.setattr(B, "cluster_resources",
                        lambda api: [{"vmid": 9000, "type": "qemu", "node": "n1"}])
    monkeypatch.setattr(B, "guest_config_get", lambda api, vmid, kind, node=None: {"name": "x"})
    monkeypatch.setattr(B, "ha_resources_list", lambda api: [])
    monkeypatch.setattr(B, "pools_list", lambda api: [{"poolid": "prod"}])  # NO members in summary
    monkeypatch.setattr(B, "pool_get", lambda api, poolid: {"members": [{"vmid": 9000}]})
    api = _FakeApi(replication=[], backup=[], snapshots=[], guest_status={"status": "stopped"})
    r = guest_destroy_blast(api, "9000", "qemu", "n1", purge=False, force=False)
    pool = [a for a in r.affected if a["kind"] == "pool"]
    assert pool and pool[0]["ref"] == "prod"


def test_gather_pool_get_failure_is_incomplete(monkeypatch):
    # If an individual pool_get fails, membership for that pool is UNKNOWN -> pools=None so compute
    # flags incomplete (never under-report by silently dropping the pool).
    import proximo.blast as B
    monkeypatch.setattr(B, "cluster_resources",
                        lambda api: [{"vmid": 9000, "type": "qemu", "node": "n1"}])
    monkeypatch.setattr(B, "guest_config_get", lambda api, vmid, kind, node=None: {"name": "x"})
    monkeypatch.setattr(B, "ha_resources_list", lambda api: [])
    monkeypatch.setattr(B, "pools_list", lambda api: [{"poolid": "prod"}])
    monkeypatch.setattr(B, "pool_get",
                        lambda api, poolid: (_ for _ in ()).throw(RuntimeError("boom")))
    api = _FakeApi(replication=[], backup=[], snapshots=[], guest_status={"status": "stopped"})
    inp = gather_guest_dependents(api, "9000", "qemu", "n1", purge=False, force=False)
    assert inp.pools is None
    r = guest_destroy_blast(api, "9000", "qemu", "n1", purge=False, force=False)
    assert r.complete is False


# ===========================================================================
# Task 10: plan_delete wiring tests
# ===========================================================================

def test_plan_delete_populates_affected_and_completes(monkeypatch):
    import proximo.blast as B
    from proximo.provisioning import plan_delete

    # found, stopped, protected guest with one HA ref; purge off
    monkeypatch.setattr(B, "cluster_resources", lambda api: [])
    monkeypatch.setattr(B, "guest_config_get", lambda api, vmid, kind, node=None: {"protection": 1})
    monkeypatch.setattr(B, "ha_resources_list", lambda api: [{"sid": "vm:9000"}])
    monkeypatch.setattr(B, "pools_list", lambda api: [])

    class _Api(_FakeApi):
        def guest_status(self, vmid, kind="lxc", node=None):
            return {"status": "stopped", "name": "tmpl"}

    api = _Api(replication=[], backup=[], snapshots=[])
    plan = plan_delete(api, "9000", "qemu", None, purge=False, force=False)
    assert plan.risk == "high"
    assert plan.affected, "Plan.affected should carry the cascade"
    kinds = {a["kind"] for a in plan.affected}
    assert "protection" in kinds and "ha" in kinds
    # protection reason folded into the plan's risk_reasons
    assert any("protection" in r.lower() for r in plan.risk_reasons)


def test_plan_delete_not_found_skips_cascade(monkeypatch):
    from proximo.provisioning import plan_delete

    class _NF(_FakeApi):
        def guest_status(self, vmid, kind="lxc", node=None):
            err = RuntimeError("404")
            class _R:
                status_code = 404
            err.response = _R()
            raise err

    plan = plan_delete(_NF(), "9000", "qemu", None, purge=False, force=False)
    assert plan.risk == "high" and not plan.affected  # no cascade on a confirmed-absent guest


def test_gather_null_data_replication_backup_normalize_to_empty(monkeypatch):
    # PVE returns {"data": null} on endpoints with no data -> api._get returns None.
    # gather must normalize None -> [] so compute reads it as confirmed-empty, NOT failed-read.
    import proximo.blast as B
    monkeypatch.setattr(B, "cluster_resources", lambda api: [])
    monkeypatch.setattr(B, "guest_config_get", lambda api, vmid, kind, node=None: {"name": "x"})
    monkeypatch.setattr(B, "ha_resources_list", lambda api: [])
    monkeypatch.setattr(B, "pools_list", lambda api: [])
    api = _FakeApi(replication=None, backup=None, snapshots=[], guest_status={"status": "stopped"})
    inp = gather_guest_dependents(api, "9000", "qemu", "n1", purge=False, force=False)
    assert inp.replication_jobs == []   # FAILS before the fix (is None)
    assert inp.backup_jobs == []        # FAILS before the fix (is None)
    r = guest_destroy_blast(api, "9000", "qemu", "n1", purge=False, force=False)
    assert r.complete is True           # no spurious 'incomplete' on a stock cluster
