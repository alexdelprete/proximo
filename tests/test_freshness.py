"""pve_backup_freshness — the backup-freshness fence (unit).

Born from a real field wound (2026-07-09): a nightly backup job reported "TASK OK" for a month
while producing NOTHING — the scheduler's word was trusted, the archives were never checked.
The fence walks ACTUAL backup archives per guest and compares their age against what the job
schedules promise. Job/task success is never treated as evidence that a backup exists.

Posture mirrors doctor/diagnose: read-only, advisory, never overclaims — and critically it
NEVER fails toward "fresh": an unreadable storage yields "unknown" + complete=False, not a
clean bill.
"""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from proximo.freshness import _cadence_hours, backup_freshness

_NOW = time.time()


def _age(hours: float) -> int:
    """ctime for an archive `hours` old."""
    return int(_NOW - hours * 3600)


def _entry(vmid, hours_old, storage="pbs", volid=None):
    return {
        "volid": volid or f"{storage}:backup/vzdump-lxc-{vmid}-x.tar.zst",
        "vmid": vmid,
        "ctime": _age(hours_old),
        "size": 1024,
    }


def _guest(vmid, node="pve", type_="lxc", name=None, pool=None, template=0):
    g = {"vmid": vmid, "node": node, "type": type_, "name": name or f"g{vmid}",
         "template": template, "status": "running"}
    if pool is not None:
        g["pool"] = pool
    return g


# Full-sight permission map: the fence's absence verdicts ("never") are only trustworthy when
# the token could have SEEN an archive if one existed — PVE filters backup volumes out of the
# content listing per-volume (Datastore.AllocateSpace on the storage + VM.Backup on the owner
# guest, or Datastore.Allocate on the storage as bypass) and returns 200 + [] otherwise.
_SIGHTED_PERMS = {"/": {"Datastore.Allocate": 1, "Datastore.AllocateSpace": 1, "VM.Backup": 1}}
# What a PVEAuditor (read-only) token actually holds — blind to backup volumes.
_AUDITOR_PERMS = {"/": {"Datastore.Audit": 1, "VM.Audit": 1, "Sys.Audit": 1}}


class _FenceApi:
    """Duck-typed ApiBackend: routes _get by path; raises for paths listed in fail_paths."""

    def __init__(self, *, jobs=(), unprotected=(), guests=(), nodes=("pve",),
                 content=None, fail_paths=(), perms=None, perms_raises=False):
        self._jobs = list(jobs)
        self._unprotected = list(unprotected)
        self._guests = list(guests)
        self._nodes = list(nodes)
        self._content = dict(content or {})  # {(node, storage): [entries]}
        self._fail_paths = set(fail_paths)
        self._perms = _SIGHTED_PERMS if perms is None else perms
        self._perms_raises = perms_raises
        self.config = SimpleNamespace(node=self._nodes[0] if self._nodes else "pve")

    def access_permissions(self, path=None):
        if self._perms_raises:
            raise RuntimeError("403 permission denied")
        return self._perms

    def _get(self, path):
        for frag in self._fail_paths:
            if frag in path:
                raise RuntimeError(f"boom: {path}")
        if path == "/cluster/backup":
            return self._jobs
        if path == "/cluster/backup-info/not-backed-up":
            return self._unprotected
        if path == "/cluster/resources?type=vm":
            return self._guests
        if path == "/cluster/resources?type=node":
            return [{"node": n} for n in self._nodes]
        if path.startswith("/nodes/"):
            # /nodes/{n}/storage/{s}/content?content=backup
            parts = path.split("/")
            node, storage = parts[2], parts[4].split("?")[0]
            return list(self._content.get((node, storage), []))
        raise AssertionError(f"unexpected path: {path}")


def _job(job_id="nightly", schedule="02:30", storage="pbs", **kw):
    return {"id": job_id, "schedule": schedule, "storage": storage, **kw}


def _one(report, vmid):
    matches = [g for g in report["guests"] if g["vmid"] == str(vmid)]
    assert len(matches) == 1, f"guest {vmid} not uniquely in report: {report['guests']}"
    return matches[0]


# ---------------------------------------------------------------------------
# Verdicts
# ---------------------------------------------------------------------------

def test_fresh_guest_covered_by_daily_job():
    api = _FenceApi(
        jobs=[_job(vmid="101")],
        guests=[_guest(101)],
        content={("pve", "pbs"): [_entry(101, 2)]},
    )
    out = backup_freshness(api)
    g = _one(out, 101)
    assert g["verdict"] == "fresh"
    assert g["covered_by"] == ["nightly"]
    assert abs(g["newest_backup"]["age_hours"] - 2.0) < 0.1
    # daily cadence (24) + default grace (6)
    assert g["expected_max_age_hours"] == 30.0
    assert out["counts"]["fresh"] == 1
    assert out["complete"] is True


def test_stale_guest_is_flagged():
    api = _FenceApi(
        jobs=[_job(vmid="101")],
        guests=[_guest(101)],
        content={("pve", "pbs"): [_entry(101, 80)]},
    )
    out = backup_freshness(api)
    g = _one(out, 101)
    assert g["verdict"] == "stale"
    assert out["counts"]["stale"] == 1
    assert any("101" in f and "stale" in f.lower() for f in out["flags"])


def test_covered_but_never_backed_up():
    """The field case in miniature: a job exists and is enabled, zero archives exist."""
    api = _FenceApi(
        jobs=[_job(vmid="101")],
        guests=[_guest(101)],
        content={("pve", "pbs"): []},
    )
    out = backup_freshness(api)
    g = _one(out, 101)
    assert g["verdict"] == "never"
    assert g["newest_backup"] is None
    assert any("101" in f and "never" in f.lower() for f in out["flags"])


def test_uncovered_guest():
    api = _FenceApi(
        jobs=[_job(vmid="101")],
        unprotected=[{"vmid": 102, "name": "g102", "type": "lxc"}],
        guests=[_guest(101), _guest(102)],
        content={("pve", "pbs"): [_entry(101, 2)]},
    )
    out = backup_freshness(api)
    g = _one(out, 102)
    assert g["verdict"] == "uncovered"
    assert g["covered_by"] == []
    assert any("102" in f and ("no enabled backup job" in f.lower() or "uncovered" in f.lower())
               for f in out["flags"])


def test_disabled_job_is_not_coverage():
    api = _FenceApi(
        jobs=[_job(vmid="101", enabled=0)],
        guests=[_guest(101)],
        content={("pve", "pbs"): [_entry(101, 2)]},
    )
    out = backup_freshness(api)
    g = _one(out, 101)
    assert g["verdict"] == "uncovered"
    assert any("disabled" in f.lower() for f in out["flags"])


def test_unreadable_storage_is_unknown_never_fresh():
    """An unreadable storage must NOT produce a clean bill — that's the silent-failure sin."""
    api = _FenceApi(
        jobs=[_job(vmid="101")],
        guests=[_guest(101)],
        fail_paths=("/storage/pbs/content",),
    )
    out = backup_freshness(api)
    g = _one(out, 101)
    assert g["verdict"] == "unknown"
    assert out["complete"] is False
    assert out["unreadable"] and out["unreadable"][0]["storage"] == "pbs"
    assert any("unknown" in f.lower() or "unread" in f.lower() for f in out["flags"])


def test_jobs_unreadable_means_incomplete_not_green():
    api = _FenceApi(
        guests=[_guest(101)],
        fail_paths=("/cluster/backup",),
    )
    out = backup_freshness(api)
    assert out["complete"] is False
    assert any("backup job" in f.lower() for f in out["flags"])
    assert out["counts"].get("fresh", 0) == 0


# ---------------------------------------------------------------------------
# Coverage selection semantics
# ---------------------------------------------------------------------------

def test_all_selection_with_exclude():
    api = _FenceApi(
        jobs=[_job(all=1, exclude="103")],
        guests=[_guest(101), _guest(102), _guest(103)],
        content={("pve", "pbs"): [_entry(101, 1), _entry(102, 1)]},
    )
    out = backup_freshness(api)
    assert _one(out, 101)["verdict"] == "fresh"
    assert _one(out, 102)["verdict"] == "fresh"
    assert _one(out, 103)["verdict"] == "uncovered"


def test_pool_selection():
    api = _FenceApi(
        jobs=[_job(pool="prod")],
        guests=[_guest(101, pool="prod"), _guest(102)],
        content={("pve", "pbs"): [_entry(101, 1)]},
    )
    out = backup_freshness(api)
    assert _one(out, 101)["verdict"] == "fresh"
    assert _one(out, 102)["verdict"] == "uncovered"


def test_node_pinned_job_only_covers_that_node():
    api = _FenceApi(
        jobs=[_job(vmid="101,102", node="pve2")],
        guests=[_guest(101, node="pve"), _guest(102, node="pve2")],
        nodes=("pve", "pve2"),
        content={("pve2", "pbs"): [_entry(102, 1)]},
    )
    out = backup_freshness(api)
    assert _one(out, 101)["verdict"] == "uncovered"
    assert _one(out, 102)["verdict"] == "fresh"


def test_vmid_normalization_int_vs_str():
    api = _FenceApi(
        jobs=[_job(vmid="101")],
        guests=[_guest(101)],  # int vmid from resources
        content={("pve", "pbs"): [_entry("101", 1)]},  # str vmid from content
    )
    out = backup_freshness(api)
    assert _one(out, 101)["verdict"] == "fresh"


def test_templates_are_skipped():
    api = _FenceApi(
        jobs=[_job(all=1)],
        guests=[_guest(101), _guest(900, template=1)],
        content={("pve", "pbs"): [_entry(101, 1)]},
    )
    out = backup_freshness(api)
    assert [g["vmid"] for g in out["guests"]] == ["101"]


def test_pve_not_backed_up_disagreement_is_flagged():
    """PVE's own coverage read wins when it disagrees with our parse — flagged, not hidden."""
    api = _FenceApi(
        jobs=[_job(vmid="101")],
        unprotected=[{"vmid": 101, "name": "g101", "type": "lxc"}],
        guests=[_guest(101)],
        content={("pve", "pbs"): [_entry(101, 1)]},
    )
    out = backup_freshness(api)
    assert _one(out, 101)["verdict"] == "uncovered"
    assert any("disagree" in f.lower() or "cross-check" in f.lower() for f in out["flags"])


def test_not_backed_up_read_failure_is_disclosed_not_fatal():
    api = _FenceApi(
        jobs=[_job(vmid="101")],
        guests=[_guest(101)],
        content={("pve", "pbs"): [_entry(101, 1)]},
        fail_paths=("not-backed-up",),
    )
    out = backup_freshness(api)
    assert _one(out, 101)["verdict"] == "fresh"
    assert out["complete"] is True
    assert any("cross-check" in f.lower() for f in out["flags"])


# ---------------------------------------------------------------------------
# Token sight — a blind token must never produce a false "never" (live-found 2026-07-09:
# a PVEAuditor token walked a healthy PBS storage and saw 25 guests as "never backed up")
# ---------------------------------------------------------------------------

def test_blind_auditor_token_yields_unknown_not_never():
    api = _FenceApi(
        jobs=[_job(vmid="101")],
        guests=[_guest(101)],
        content={("pve", "pbs"): []},  # 200 + [] — exactly what PVE gives a blind token
        perms=_AUDITOR_PERMS,
    )
    out = backup_freshness(api)
    g = _one(out, 101)
    assert g["verdict"] == "unknown"
    assert out["complete"] is False
    assert any("VM.Backup" in f and "Datastore.AllocateSpace" in f for f in out["flags"])


def test_blind_token_downgrades_stale_but_keeps_fresh():
    """An archive the token CAN see is real evidence: fresh stands. But 'stale' relies on
    absence-of-a-newer-archive, which a blind covered storage could be hiding — unknown."""
    api = _FenceApi(
        jobs=[_job(job_id="a", vmid="101", storage="pbs"),
              _job(job_id="b", vmid="102", storage="pbs")],
        guests=[_guest(101), _guest(102)],
        content={("pve", "pbs"): [_entry(101, 2), _entry(102, 500)]},
        perms=_AUDITOR_PERMS,
    )
    out = backup_freshness(api)
    assert _one(out, 101)["verdict"] == "fresh"      # found + young: evidence stands
    assert _one(out, 102)["verdict"] == "unknown"    # looks stale, but sight unproven


def test_datastore_allocate_bypass_counts_as_sight():
    api = _FenceApi(
        jobs=[_job(vmid="101")],
        guests=[_guest(101)],
        content={("pve", "pbs"): []},
        perms={"/storage/pbs": {"Datastore.Allocate": 1}},
    )
    out = backup_freshness(api)
    assert _one(out, 101)["verdict"] == "never"


def test_scoped_sight_grants_on_exact_paths():
    api = _FenceApi(
        jobs=[_job(vmid="101")],
        guests=[_guest(101)],
        content={("pve", "pbs"): []},
        perms={"/storage/pbs": {"Datastore.AllocateSpace": 1},
               "/vms/101": {"VM.Backup": 1}},
    )
    out = backup_freshness(api)
    assert _one(out, 101)["verdict"] == "never"


def test_unreadable_perms_treated_as_blind():
    api = _FenceApi(
        jobs=[_job(vmid="101")],
        guests=[_guest(101)],
        content={("pve", "pbs"): []},
        perms_raises=True,
    )
    out = backup_freshness(api)
    assert _one(out, 101)["verdict"] == "unknown"
    assert out["complete"] is False
    assert any("permission" in f.lower() for f in out["flags"])


# ---------------------------------------------------------------------------
# Freshness evidence
# ---------------------------------------------------------------------------

def test_newest_archive_wins_across_storages_and_nodes():
    api = _FenceApi(
        jobs=[_job(job_id="a", vmid="101", storage="local"),
              _job(job_id="b", vmid="101", storage="pbs")],
        guests=[_guest(101)],
        nodes=("pve", "pve2"),
        content={
            ("pve", "local"): [_entry(101, 50, storage="local")],
            ("pve", "pbs"): [_entry(101, 2)],
            ("pve2", "pbs"): [_entry(101, 2)],  # shared storage seen from both nodes
        },
    )
    out = backup_freshness(api)
    g = _one(out, 101)
    assert g["verdict"] == "fresh"
    assert g["newest_backup"]["storage"] == "pbs"
    assert abs(g["newest_backup"]["age_hours"] - 2.0) < 0.1


def test_override_max_age_wins_over_schedule():
    api = _FenceApi(
        jobs=[_job(vmid="101")],
        guests=[_guest(101)],
        content={("pve", "pbs"): [_entry(101, 2)]},
    )
    out = backup_freshness(api, max_age_hours=1.0)
    assert _one(out, 101)["verdict"] == "stale"
    assert _one(out, 101)["expected_max_age_hours"] == 1.0


def test_strictest_covering_job_sets_expectation():
    api = _FenceApi(
        jobs=[_job(job_id="hourly-job", schedule="hourly", vmid="101"),
              _job(job_id="weekly-job", schedule="sun 03:00", vmid="101")],
        guests=[_guest(101)],
        content={("pve", "pbs"): [_entry(101, 12)]},
    )
    out = backup_freshness(api)
    g = _one(out, 101)
    # hourly (1) + grace (6) = 7h is the strictest promise; 12h-old archive breaks it
    assert g["expected_max_age_hours"] == 7.0
    assert g["verdict"] == "stale"


# ---------------------------------------------------------------------------
# Schedule -> cadence heuristic
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("schedule,hours", [
    ("02:30", 24.0),           # bare time = daily
    ("daily", 24.0),
    ("21:00,03:00", 24.0),     # multiple times a day: still promise >= daily
    ("hourly", 1.0),
    ("*/2:00", 2.0),           # every N hours
    ("2,22:30", 24.0),         # hour-only + H:MM mixed, twice daily (live form, real infra)
    ("2", 24.0),               # a single bare hour = daily at 02:00
])
def test_cadence_simple_forms(schedule, hours):
    got, source = _cadence_hours(schedule)
    assert got == hours
    # A recognized form must not carry the "assumed" hedge — same hours, honest confidence.
    assert "assumed" not in source


def test_cadence_weekly_forms():
    assert _cadence_hours("mon 03:00")[0] == 168.0
    assert _cadence_hours("sat,sun 05:00")[0] == 168.0  # conservative: never promise tighter
    assert _cadence_hours("mon..fri 02:30")[0] == 168.0


def test_cadence_unknown_is_assumed_daily_and_disclosed():
    hours, source = _cadence_hours("when-the-moon-is-full")
    assert hours == 24.0
    assert "assumed" in source


def test_cadence_legacy_dow_jobs():
    api = _FenceApi(
        jobs=[{"id": "legacy", "storage": "pbs", "vmid": "101",
               "dow": "mon,tue,wed,thu,fri,sat,sun", "starttime": "02:30"}],
        guests=[_guest(101)],
        content={("pve", "pbs"): [_entry(101, 2)]},
    )
    out = backup_freshness(api)
    g = _one(out, 101)
    assert g["expected_max_age_hours"] == 30.0  # all-7-days dow = daily
    assert g["verdict"] == "fresh"


# ---------------------------------------------------------------------------
# Posture
# ---------------------------------------------------------------------------

def test_note_says_archives_are_the_evidence():
    api = _FenceApi(jobs=[], guests=[])
    out = backup_freshness(api)
    note = out["note"].lower()
    assert "archive" in note
    assert "task" in note  # the "TASK OK is not evidence" honesty line
    # Population honesty (live-found 2026-07-09: a scoped /vms grant silently shrank the guest
    # list from 25 to 6 — deeper-path ACLs REPLACE inherited ones): the fence must disclose
    # that its population is only what the token can enumerate.
    assert "vm.audit" in note
    assert out["guests_visible"] == 0


def test_guests_visible_counts_the_enumerable_population():
    api = _FenceApi(
        jobs=[_job(vmid="101")],
        guests=[_guest(101), _guest(900, template=1)],
        content={("pve", "pbs"): [_entry(101, 1)]},
    )
    out = backup_freshness(api)
    assert out["guests_visible"] == 1  # templates excluded; hidden guests can't be counted


def test_pve_backup_freshness_records_read_to_ledger(tmp_path, monkeypatch):
    """Seam: the tool through the server records to the PROVE ledger as a read (mutation=False)."""
    import json

    import proximo.server as server
    from proximo.audit import AuditLedger
    from proximo.config import ProximoConfig

    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(api_base_url="https://x:8006/api2/json", node="pve", token_path="/run/x",
                        audit_log_path=log)
    api = _FenceApi(
        jobs=[_job(vmid="101")],
        guests=[_guest(101)],
        content={("pve", "pbs"): [_entry(101, 2)]},
    )
    api.config = cfg
    ledger = AuditLedger(log)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, api, None, ledger))

    out = server.pve_backup_freshness()
    assert out["counts"]["fresh"] == 1
    with open(log, encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]
    assert any(e["action"] == "pve_backup_freshness" and e["outcome"] == "ok"
               and e["mutation"] is False for e in entries)


def test_jobs_are_reported_with_cadence():
    api = _FenceApi(
        jobs=[_job(vmid="101")],
        guests=[_guest(101)],
        content={("pve", "pbs"): [_entry(101, 1)]},
    )
    out = backup_freshness(api)
    (j,) = out["jobs"]
    assert j["id"] == "nightly"
    assert j["cadence_hours"] == 24.0
    assert j["max_age_hours"] == 30.0
    assert j["enabled"] is True


# ---------------------------------------------------------------------------
# 2026-07-10 audit — fence gaps (M3 sub-daily cadence, M6 node-sight, L13, L21)
# ---------------------------------------------------------------------------

def test_cadence_sub_daily_every_30_min_is_hourly_or_tighter():
    # M3: '*:0/30' = every 30 min. Falling back to assumed-daily (24h) makes a 12h-stale hourly
    # backup read 'fresh' — a false-fresh, the fence's cardinal sin.
    hrs, _ = _cadence_hours("*:0/30")
    assert hrs <= 1.0


def test_cadence_hourly_star_minute():
    hrs, _ = _cadence_hours("*:00")
    assert hrs <= 1.0


def test_cadence_every_4_hours_step_form():
    hrs, _ = _cadence_hours("0/4:00")
    assert hrs == 4.0


def test_sub_daily_schedule_stale_not_falsely_fresh():
    # M3 end-to-end: hourly job, newest archive 12h old -> STALE, not fresh.
    api = _FenceApi(jobs=[_job(vmid="101", schedule="*:00")], guests=[_guest(101)],
                    content={("pve", "pbs"): [_entry(101, 12)]})
    out = backup_freshness(api)
    assert _one(out, 101)["verdict"] == "stale"


def test_empty_node_enumeration_flags_and_incomplete():
    # M6: a token that cannot list cluster nodes gets 200 + [] -> the archive walk silently collapses
    # to one node. Must flag it and set complete=False, not report false never/stale as complete.
    api = _FenceApi(jobs=[_job(vmid="101")], guests=[_guest(101)], nodes=[],
                    content={("pve", "pbs"): [_entry(101, 2)]})
    out = backup_freshness(api)
    assert out["complete"] is False
    assert any("node" in f.lower() for f in out["flags"])


def test_stale_becomes_unknown_when_a_covering_storage_is_unreadable():
    # L13: newest VISIBLE archive is old (stale), but a covering storage was unreadable — a newer
    # archive may exist there, so the verdict must degrade to 'unknown', not assert 'stale'.
    api = _FenceApi(
        jobs=[_job(job_id="j1", vmid="101", storage="pbs"),
              _job(job_id="j2", vmid="101", storage="pbs2")],
        guests=[_guest(101)],
        content={("pve", "pbs"): [_entry(101, 80)]},
        fail_paths=("/storage/pbs2/",),
    )
    out = backup_freshness(api)
    assert _one(out, 101)["verdict"] == "unknown"


def test_guest_list_unreadable_is_fatal_and_incomplete():
    # L21: the guest list itself is unreadable -> the fence cannot run: complete=False, all counts
    # zero, a clear flag, and nothing claimed verified. (Characterization test for the fatal path.)
    api = _FenceApi(jobs=[_job(vmid="101")], guests=[_guest(101)],
                    fail_paths=("resources?type=vm",))
    out = backup_freshness(api)
    assert out["complete"] is False
    assert out["guests_visible"] == 0
    assert all(v == 0 for v in out["counts"].values())
    assert any("cannot run" in f.lower() or "unreadable" in f.lower() for f in out["flags"])
