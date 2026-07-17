"""Confirm=True sweep — pve_ceph (Waves 6a-6d, 2026-07-16 full-surface campaign; 6d CLOSES
Wave 6).

Mirrors the `_wire()` idiom in tests/test_server_plan.py:110-131 (already re-used and
review-approved in tests/test_confirm_sweep_pve_apt.py and siblings): `proximo.server._svc` is
monkeypatched to a fake api + a REAL AuditLedger in tmp_path, so a confirm=True call proves
three welds at once:
  1. return shape — status is the EXECUTED shape ("ok"/"submitted"), never "plan";
  2. the fake api captured the underlying call, EXACT payload (full tuple/dict equality) —
     pve_ceph.py calls typed methods directly (api.ceph_flags_set/api.ceph_flag_set), not the
     generic _put verb, so the fake exposes those same typed methods;
  3. the ledger recorded a confirmed mutation — structural asserts only (action, mutation,
     outcome, detail.confirmed), never exact prose.

Both mutations also call api.ceph_flags_list()/api.ceph_flag_get(flag) during their
CAPTURE-or-declare plan build (which runs on BOTH the dry-run and confirm=True paths) — the fake
answers with a small fixture so the plan build resolves without raising.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import proximo.server as server
from proximo.audit import AuditLedger
from proximo.backends import ProximoError, _check_ceph_daemon_id, _check_node
from proximo.config import ProximoConfig


class _Api:
    """Fake PVE api exposing only the ceph-plane typed methods pve_ceph.py calls directly."""

    def __init__(self, node: str = "pve"):
        self.config = SimpleNamespace(node=node)
        self.ceph_flags_sets: list[tuple] = []
        self.ceph_flag_sets: list[tuple] = []
        self.ceph_mon_creates: list[tuple] = []
        self.ceph_mon_destroys: list[tuple] = []
        self.ceph_mgr_creates: list[tuple] = []
        self.ceph_mgr_destroys: list[tuple] = []
        self.ceph_mds_creates: list[tuple] = []
        self.ceph_mds_destroys: list[tuple] = []
        self.ceph_inits: list[tuple] = []
        self.ceph_service_starts: list[tuple] = []
        self.ceph_service_stops: list[tuple] = []
        self.ceph_service_restarts: list[tuple] = []
        self.ceph_osd_creates: list[tuple] = []
        self.ceph_osd_destroys: list[tuple] = []
        self.ceph_osd_ins: list[tuple] = []
        self.ceph_osd_outs: list[tuple] = []
        self.ceph_osd_scrubs: list[tuple] = []
        self.ceph_pool_creates: list[tuple] = []
        self.ceph_pool_sets: list[tuple] = []
        self.ceph_pool_destroys: list[tuple] = []
        self.ceph_fs_creates: list[tuple] = []
        self.ceph_fs_destroys: list[tuple] = []

    def _ceph_daemon_target(self, node, explicit_id, label):
        """Mirrors ApiBackend._ceph_daemon_target byte-for-byte — the mon/mgr/mds CREATE plan
        factories call this shared resolution instead of duplicating it inline (Wave 6b review
        Nit)."""
        _check_node(node)
        n = node or self.config.node
        ident = _check_ceph_daemon_id(explicit_id, label) if explicit_id is not None else n
        return n, ident

    def ceph_flags_list(self):
        # Small fixture — enough for the CAPTURE-or-declare plan builder to resolve without
        # raising; matches the live schema's [{name, value, description}, ...] shape.
        return [
            {"name": "noout", "value": False, "description": "..."},
            {"name": "pause", "value": False, "description": "..."},
        ]

    def ceph_flag_get(self, flag):
        return False

    def ceph_flags_set(self, flags):
        self.ceph_flags_sets.append(dict(flags))
        return "UPID:pve:00007:0:0:0:cephflags:0:root@pam:"

    def ceph_flag_set(self, flag, value):
        self.ceph_flag_sets.append((flag, value))

    # --- Wave 6b: services lifecycle ---

    def ceph_mon_list(self, node=None):
        return [{"name": "pve", "host": "pve", "addr": "10.0.0.1:6789/0", "quorum": True}]

    def ceph_mgr_list(self, node=None):
        return [{"name": "pve", "host": "pve", "addr": "10.0.0.1:6800/0", "state": "active"}]

    def ceph_mds_list(self, node=None):
        return [{"name": "pve", "host": "pve", "addr": "10.0.0.1:6801/0", "state": "up:standby"}]

    def ceph_cmd_safety(self, action, service, service_id, node=None):
        return {"safe": True}

    def ceph_mon_create(self, node=None, monid=None, mon_address=None):
        self.ceph_mon_creates.append((node, monid, mon_address))
        return "UPID:pve:00010:0:0:0:cephmoncreate:0:root@pam:"

    def ceph_mon_destroy(self, monid, node=None):
        self.ceph_mon_destroys.append((monid, node))
        return "UPID:pve:00011:0:0:0:cephmondestroy:0:root@pam:"

    def ceph_mgr_create(self, node=None, mgr_id=None):
        self.ceph_mgr_creates.append((node, mgr_id))
        return "UPID:pve:00012:0:0:0:cephmgrcreate:0:root@pam:"

    def ceph_mgr_destroy(self, mgr_id, node=None):
        self.ceph_mgr_destroys.append((mgr_id, node))
        return "UPID:pve:00013:0:0:0:cephmgrdestroy:0:root@pam:"

    def ceph_mds_create(self, node=None, name=None, hotstandby=None):
        self.ceph_mds_creates.append((node, name, hotstandby))
        return "UPID:pve:00014:0:0:0:cephmdscreate:0:root@pam:"

    def ceph_mds_destroy(self, name, node=None):
        self.ceph_mds_destroys.append((name, node))
        return "UPID:pve:00015:0:0:0:cephmdsdestroy:0:root@pam:"

    def ceph_init(self, node=None, cluster_network=None, disable_cephx=None, min_size=None,
                  network=None, pg_bits=None, size=None):
        self.ceph_inits.append(
            (node, cluster_network, disable_cephx, min_size, network, pg_bits, size)
        )
        return None

    def ceph_service_start(self, node=None, service=None):
        self.ceph_service_starts.append((node, service))
        return "UPID:pve:00016:0:0:0:cephstart:0:root@pam:"

    def ceph_service_stop(self, node=None, service=None):
        self.ceph_service_stops.append((node, service))
        return "UPID:pve:00017:0:0:0:cephstop:0:root@pam:"

    def ceph_service_restart(self, node=None, service=None):
        self.ceph_service_restarts.append((node, service))
        return "UPID:pve:00018:0:0:0:cephrestart:0:root@pam:"

    # --- Wave 6c: OSD ---

    def ceph_osd_tree(self, node=None):
        # Small nested fixture — enough for the CAPTURE-or-declare plan builder to resolve
        # without raising; matches the live schema's root->children CRUSH-bucket shape.
        return {"root": {"id": -1, "children": [
            {"id": 0, "name": "osd.0", "status": "up"},
            {"id": 1, "name": "osd.1", "status": "up"},
        ]}}

    def ceph_osd_create(self, dev=None, node=None, crush_device_class=None, db_dev=None,
                         db_dev_size=None, wal_dev=None, wal_dev_size=None, encrypted=None,
                         osds_per_device=None):
        self.ceph_osd_creates.append((dev, node, crush_device_class, db_dev, db_dev_size,
                                       wal_dev, wal_dev_size, encrypted, osds_per_device))
        return "UPID:pve:00019:0:0:0:cephosdcreate:0:root@pam:"

    def ceph_osd_destroy(self, osdid, node=None, cleanup=None):
        self.ceph_osd_destroys.append((osdid, node, cleanup))
        return "UPID:pve:00020:0:0:0:cephosddestroy:0:root@pam:"

    def ceph_osd_in(self, osdid, node=None):
        self.ceph_osd_ins.append((osdid, node))
        return None

    def ceph_osd_out(self, osdid, node=None):
        self.ceph_osd_outs.append((osdid, node))
        return None

    def ceph_osd_scrub(self, osdid, node=None, deep=None):
        self.ceph_osd_scrubs.append((osdid, node, deep))
        return None

    # --- Wave 6d: pools + CephFS ---

    def ceph_pool_list(self, node=None):
        # Small fixture — enough for the CAPTURE-or-declare plan builder to resolve without
        # raising; matches the live schema's pool-list shape.
        return [{"pool": 1, "pool_name": "rbd", "type": "replicated", "size": 3, "min_size": 2,
                 "pg_num": 128, "crush_rule": 0, "crush_rule_name": "replicated_rule"}]

    def ceph_pool_status(self, name, node=None, verbose=None):
        # crush_rule is a STRING here (title "Crush Rule Name," matching the write side) -- NOT
        # an integer, unlike ceph_pool_list above. Wave 6d review Finding 2 (2026-07-17): the
        # pre-fix fixture wrongly used an int, matching a wrong docstring claim nothing in the
        # suite could catch.
        return {"id": 1, "name": name, "application": "rbd", "crush_rule": "replicated_rule",
                "min_size": 2, "size": 3, "pg_num": 128, "pg_autoscale_mode": "warn"}

    def ceph_fs_list(self, node=None):
        return [{"name": "cephfs", "metadata_pool": "cephfs_metadata", "metadata_pool_id": 2,
                 "data_pool": "cephfs_data", "data_pool_ids": [3], "data_pools": ["cephfs_data"]}]

    def ceph_pool_create(self, name=None, node=None, add_storages=None, application=None,
                          crush_rule=None, erasure_coding=None, min_size=None,
                          pg_autoscale_mode=None, pg_num=None, pg_num_min=None, size=None,
                          target_size=None, target_size_ratio=None):
        self.ceph_pool_creates.append((
            name, node, add_storages, application, crush_rule, erasure_coding, min_size,
            pg_autoscale_mode, pg_num, pg_num_min, size, target_size, target_size_ratio,
        ))
        return "UPID:pve:00021:0:0:0:cephpoolcreate:0:root@pam:"

    def ceph_pool_set(self, name=None, node=None, application=None, crush_rule=None,
                       min_size=None, pg_autoscale_mode=None, pg_num=None, pg_num_min=None,
                       size=None, target_size=None, target_size_ratio=None):
        self.ceph_pool_sets.append((
            name, node, application, crush_rule, min_size, pg_autoscale_mode, pg_num,
            pg_num_min, size, target_size, target_size_ratio,
        ))
        return "UPID:pve:00022:0:0:0:cephpoolset:0:root@pam:"

    def ceph_pool_destroy(self, name, node=None, force=None, remove_ecprofile=None,
                           remove_storages=None):
        self.ceph_pool_destroys.append((name, node, force, remove_ecprofile, remove_storages))
        return "UPID:pve:00023:0:0:0:cephpooldestroy:0:root@pam:"

    def ceph_fs_create(self, node=None, name=None, add_storage=None, pg_num=None):
        self.ceph_fs_creates.append((node, name, add_storage, pg_num))
        return "UPID:pve:00024:0:0:0:cephfscreate:0:root@pam:"

    def ceph_fs_destroy(self, name, node=None, remove_pools=None, remove_storages=None):
        self.ceph_fs_destroys.append((name, node, remove_pools, remove_storages))
        return "UPID:pve:00025:0:0:0:cephfsdestroy:0:root@pam:"


def _wire(tmp_path, monkeypatch):
    """The `_wire()` idiom from tests/test_server_plan.py:110-131."""
    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(
        api_base_url="https://x:8006/api2/json", node="pve", token_path="/run/x",
        ct_allowlist=frozenset({"*"}), audit_log_path=log,
    )
    api = _Api()
    exec_ = SimpleNamespace()  # unused by these wrappers
    ledger = AuditLedger(log)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, api, exec_, ledger))
    return cfg, api, ledger, log


def _entries(log: str) -> list[dict]:
    with open(log, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _confirmed_entry(log: str, action: str, outcome: str) -> dict:
    entries = [e for e in _entries(log) if e["action"] == action and e["outcome"] == outcome]
    assert len(entries) == 1, f"expected exactly one {action!r}/{outcome!r} ledger entry, got {entries}"
    return entries[0]


# ---------------------------------------------------------------------------
# pve_ceph_flags_set — typed-method capture, async (task UPID) outcome, bulk.
# ---------------------------------------------------------------------------


def test_flags_set_confirm_executes_forwards_exact_payload_and_records(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)

    out = server.pve_ceph_flags_set(noout=True, pause=False, nodeep_scrub=True, confirm=True)

    assert out["status"] == "submitted"
    assert out["status"] != "plan"
    assert out["result"] == "UPID:pve:00007:0:0:0:cephflags:0:root@pam:"

    assert api.ceph_flags_sets, "pve_ceph_flags_set confirm=True never reached api.ceph_flags_set"
    # exact: nodeep_scrub translates to the wire-hyphenated 'nodeep-scrub' key; every other flag
    # left None (untouched) must NOT appear in the forwarded payload at all.
    assert api.ceph_flags_sets[-1] == {"noout": True, "pause": False, "nodeep-scrub": True}

    entry = _confirmed_entry(log, "pve_ceph_flags_set", "submitted")
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True
    assert entry["detail"]["changes"] == {"noout": True, "pause": False, "nodeep-scrub": True}


def test_flags_set_confirm_sync_reports_ok_not_submitted(tmp_path, monkeypatch):
    """ceph_flags_set() may return None (backends.py types it `str | None` defensively) rather
    than a task UPID — a fixed outcome="submitted" would falsely claim an in-flight task."""
    _, api, _, log = _wire(tmp_path, monkeypatch)
    monkeypatch.setattr(api, "ceph_flags_set", lambda flags: None)

    out = server.pve_ceph_flags_set(noout=True, confirm=True)

    assert out["status"] == "ok"
    assert out["status"] != "submitted"
    assert out["result"] is None

    entry = _confirmed_entry(log, "pve_ceph_flags_set", "ok")
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True


def test_flags_set_omitted_flags_never_reach_the_wire(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    server.pve_ceph_flags_set(pause=True, confirm=True)
    assert api.ceph_flags_sets[-1] == {"pause": True}


# ---------------------------------------------------------------------------
# pve_ceph_flag_set — typed-method capture, synchronous ("ok") outcome, single flag.
# ---------------------------------------------------------------------------


def test_flag_set_confirm_executes_forwards_exact_payload_and_records(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)

    out = server.pve_ceph_flag_set(flag="noout", value=True, confirm=True)

    assert out["status"] == "ok"
    assert out["status"] != "plan"
    assert out["result"] is None

    assert api.ceph_flag_sets, "pve_ceph_flag_set confirm=True never reached api.ceph_flag_set"
    assert api.ceph_flag_sets[-1] == ("noout", True)

    entry = _confirmed_entry(log, "pve_ceph_flag_set", "ok")
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True
    assert entry["detail"]["flag"] == "noout"
    assert entry["detail"]["value"] is True


@pytest.mark.parametrize(
    "tool_name,kwargs",
    [
        ("pve_ceph_flags_set", {"noout": True}),
        ("pve_ceph_flag_set", {"flag": "noout", "value": True}),
    ],
)
def test_confirm_true_never_returns_plan_status(tmp_path, monkeypatch, tool_name, kwargs):
    """Cross-check (table-driven, matching the sibling confirm-sweep files' style): every ceph
    mutation's confirm=True path returns something other than "plan"."""
    _wire(tmp_path, monkeypatch)
    fn = getattr(server, tool_name)
    out = fn(confirm=True, **kwargs)
    assert out["status"] != "plan"


def test_one_shot_confirm_records_plan_before_executing(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    server.pve_ceph_flag_set(flag="pause", value=True, confirm=True)
    outcomes = {e["outcome"] for e in _entries(log) if e["action"] == "pve_ceph_flag_set"}
    assert "planned" in outcomes, "one-shot confirm must record a plan entry before executing"
    assert "ok" in outcomes


# ---------------------------------------------------------------------------
# Wave 6b — services lifecycle. Same three-weld proof per mutation: executed shape, exact
# forwarded payload via the fake's typed method, and a confirmed ledger entry.
# ---------------------------------------------------------------------------


def test_mon_create_confirm_executes_forwards_exact_payload_and_records(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)

    out = server.pve_ceph_mon_create(monid="mon-b", mon_address="10.0.0.5", confirm=True)

    assert out["status"] == "submitted"
    assert out["result"] == "UPID:pve:00010:0:0:0:cephmoncreate:0:root@pam:"
    assert api.ceph_mon_creates == [(None, "mon-b", "10.0.0.5")]

    entry = _confirmed_entry(log, "pve_ceph_mon_create", "submitted")
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True
    assert entry["detail"]["monid"] == "mon-b"
    assert entry["detail"]["mon_address"] == "10.0.0.5"


def test_mon_create_defaults_monid_to_node_on_the_wire(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    server.pve_ceph_mon_create(confirm=True)
    # the wrapper forwards the RAW None through to api.ceph_mon_create — the backend/plan layer
    # resolves the nodename default, not the wrapper (see ceph.py's "Build nuance" docstring).
    assert api.ceph_mon_creates == [(None, None, None)]


def test_mon_destroy_confirm_executes_forwards_exact_payload_and_records(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)

    out = server.pve_ceph_mon_destroy(monid="pve", confirm=True)

    assert out["status"] == "submitted"
    assert out["result"] == "UPID:pve:00011:0:0:0:cephmondestroy:0:root@pam:"
    assert api.ceph_mon_destroys == [("pve", None)]

    entry = _confirmed_entry(log, "pve_ceph_mon_destroy", "submitted")
    assert entry["mutation"] is True
    assert entry["detail"]["monid"] == "pve"
    assert entry["detail"]["confirmed"] is True


def test_mgr_create_confirm_executes_forwards_exact_payload_and_records(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)

    out = server.pve_ceph_mgr_create(mgr_id="mgr-b", confirm=True)

    assert out["status"] == "submitted"
    assert out["result"] == "UPID:pve:00012:0:0:0:cephmgrcreate:0:root@pam:"
    assert api.ceph_mgr_creates == [(None, "mgr-b")]

    entry = _confirmed_entry(log, "pve_ceph_mgr_create", "submitted")
    assert entry["detail"]["mgr_id"] == "mgr-b"
    assert entry["detail"]["confirmed"] is True


def test_mgr_destroy_confirm_executes_forwards_exact_payload_and_records(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)

    out = server.pve_ceph_mgr_destroy(mgr_id="pve", confirm=True)

    assert out["status"] == "submitted"
    assert out["result"] == "UPID:pve:00013:0:0:0:cephmgrdestroy:0:root@pam:"
    assert api.ceph_mgr_destroys == [("pve", None)]

    entry = _confirmed_entry(log, "pve_ceph_mgr_destroy", "submitted")
    assert entry["detail"]["mgr_id"] == "pve"
    assert entry["detail"]["confirmed"] is True


def test_mds_create_confirm_executes_forwards_exact_payload_and_records(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)

    out = server.pve_ceph_mds_create(name="mds-b", hotstandby=True, confirm=True)

    assert out["status"] == "submitted"
    assert out["result"] == "UPID:pve:00014:0:0:0:cephmdscreate:0:root@pam:"
    assert api.ceph_mds_creates == [(None, "mds-b", True)]

    entry = _confirmed_entry(log, "pve_ceph_mds_create", "submitted")
    assert entry["detail"]["name"] == "mds-b"
    assert entry["detail"]["hotstandby"] is True
    assert entry["detail"]["confirmed"] is True


def test_mds_destroy_confirm_executes_forwards_exact_payload_and_records(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)

    out = server.pve_ceph_mds_destroy(name="pve", confirm=True)

    assert out["status"] == "submitted"
    assert out["result"] == "UPID:pve:00015:0:0:0:cephmdsdestroy:0:root@pam:"
    assert api.ceph_mds_destroys == [("pve", None)]

    entry = _confirmed_entry(log, "pve_ceph_mds_destroy", "submitted")
    assert entry["detail"]["name"] == "pve"
    assert entry["detail"]["confirmed"] is True


def test_init_confirm_executes_forwards_exact_payload_and_records(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)

    out = server.pve_ceph_init(
        network="10.0.0.0/24", cluster_network="10.99.99.0/24",
        disable_cephx=False, min_size=2, pg_bits=8, size=3, confirm=True,
    )

    assert out["status"] == "ok"
    assert out["status"] != "submitted"
    assert out["result"] is None
    assert api.ceph_inits == [(None, "10.99.99.0/24", False, 2, "10.0.0.0/24", 8, 3)]

    entry = _confirmed_entry(log, "pve_ceph_init", "ok")
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True
    assert entry["detail"]["network"] == "10.0.0.0/24"
    assert entry["detail"]["cluster_network"] == "10.99.99.0/24"
    assert entry["detail"]["min_size"] == 2
    assert entry["detail"]["pg_bits"] == 8
    assert entry["detail"]["size"] == 3


def test_init_confirm_reports_submitted_if_a_upid_ever_comes_back(tmp_path, monkeypatch):
    """ceph_init() is documented returns:null, but the callable-outcome idiom (the 5d
    pbs_job_run lesson) must still report "submitted" honestly if a UPID ever does come back,
    rather than hardcoding "ok"."""
    _, api, _, log = _wire(tmp_path, monkeypatch)
    monkeypatch.setattr(
        api, "ceph_init", lambda *a, **kw: "UPID:pve:surprise:0:0:0:cephinit:0:root@pam:"
    )

    out = server.pve_ceph_init(confirm=True)

    assert out["status"] == "submitted"
    assert out["result"] == "UPID:pve:surprise:0:0:0:cephinit:0:root@pam:"
    entry = _confirmed_entry(log, "pve_ceph_init", "submitted")
    assert entry["mutation"] is True


def test_service_start_confirm_executes_forwards_exact_payload_and_records(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)

    out = server.pve_ceph_service_start(service="mon.pve1", confirm=True)

    assert out["status"] == "submitted"
    assert out["result"] == "UPID:pve:00016:0:0:0:cephstart:0:root@pam:"
    assert api.ceph_service_starts == [(None, "mon.pve1")]

    entry = _confirmed_entry(log, "pve_ceph_service_start", "submitted")
    assert entry["detail"]["service"] == "mon.pve1"
    assert entry["detail"]["confirmed"] is True


def test_service_start_defaults_service_to_ceph_target_in_ledger_detail(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    server.pve_ceph_service_start(confirm=True)
    assert api.ceph_service_starts == [(None, None)]
    entry = _confirmed_entry(log, "pve_ceph_service_start", "submitted")
    assert entry["detail"]["service"] == "ceph.target"


def test_service_stop_confirm_executes_forwards_exact_payload_and_records(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)

    out = server.pve_ceph_service_stop(service="osd.3", confirm=True)

    assert out["status"] == "submitted"
    assert out["result"] == "UPID:pve:00017:0:0:0:cephstop:0:root@pam:"
    assert api.ceph_service_stops == [(None, "osd.3")]

    entry = _confirmed_entry(log, "pve_ceph_service_stop", "submitted")
    assert entry["detail"]["service"] == "osd.3"
    assert entry["detail"]["confirmed"] is True


def test_service_restart_confirm_executes_forwards_exact_payload_and_records(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)

    out = server.pve_ceph_service_restart(service="mds.pve", confirm=True)

    assert out["status"] == "submitted"
    assert out["result"] == "UPID:pve:00018:0:0:0:cephrestart:0:root@pam:"
    assert api.ceph_service_restarts == [(None, "mds.pve")]

    entry = _confirmed_entry(log, "pve_ceph_service_restart", "submitted")
    assert entry["detail"]["service"] == "mds.pve"
    assert entry["detail"]["confirmed"] is True


@pytest.mark.parametrize(
    "tool_name,kwargs",
    [
        ("pve_ceph_mon_create", {}),
        ("pve_ceph_mon_destroy", {"monid": "pve"}),
        ("pve_ceph_mgr_create", {}),
        ("pve_ceph_mgr_destroy", {"mgr_id": "pve"}),
        ("pve_ceph_mds_create", {}),
        ("pve_ceph_mds_destroy", {"name": "pve"}),
        ("pve_ceph_init", {}),
        ("pve_ceph_service_start", {}),
        ("pve_ceph_service_stop", {}),
        ("pve_ceph_service_restart", {}),
    ],
)
def test_wave_6b_confirm_true_never_returns_plan_status(tmp_path, monkeypatch, tool_name, kwargs):
    """Cross-check (table-driven, matching the sibling confirm-sweep files' style): every Wave
    6b ceph mutation's confirm=True path returns something other than "plan"."""
    _wire(tmp_path, monkeypatch)
    fn = getattr(server, tool_name)
    out = fn(confirm=True, **kwargs)
    assert out["status"] != "plan"


def test_wave_6b_one_shot_confirm_records_plan_before_executing(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    server.pve_ceph_mon_destroy(monid="pve", confirm=True)
    outcomes = {e["outcome"] for e in _entries(log) if e["action"] == "pve_ceph_mon_destroy"}
    assert "planned" in outcomes, "one-shot confirm must record a plan entry before executing"
    assert "submitted" in outcomes


# ---------------------------------------------------------------------------
# Wave 6c — OSD. Same three-weld proof per mutation: executed shape, exact forwarded payload via
# the fake's typed method, and a confirmed ledger entry.
# ---------------------------------------------------------------------------


def test_osd_create_confirm_executes_forwards_exact_payload_and_records(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)

    out = server.pve_ceph_osd_create(
        dev="/dev/sdb", crush_device_class="ssd", db_dev="/dev/sdc", db_dev_size=10,
        encrypted=True, confirm=True,
    )

    assert out["status"] == "submitted"
    assert out["result"] == "UPID:pve:00019:0:0:0:cephosdcreate:0:root@pam:"
    assert api.ceph_osd_creates == [
        ("/dev/sdb", None, "ssd", "/dev/sdc", 10, None, None, True, None)
    ]

    entry = _confirmed_entry(log, "pve_ceph_osd_create", "submitted")
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True
    assert entry["detail"]["dev"] == "/dev/sdb"
    assert entry["detail"]["crush_device_class"] == "ssd"
    assert entry["detail"]["db_dev"] == "/dev/sdc"
    assert entry["detail"]["db_dev_size"] == 10
    assert entry["detail"]["encrypted"] is True


def test_osd_create_minimal_call_forwards_none_for_omitted_optionals(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    server.pve_ceph_osd_create(dev="/dev/sdb", confirm=True)
    assert api.ceph_osd_creates == [("/dev/sdb", None, None, None, None, None, None, None, None)]


def test_osd_destroy_confirm_executes_forwards_exact_payload_and_records(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)

    out = server.pve_ceph_osd_destroy(osdid=1, cleanup=True, confirm=True)

    assert out["status"] == "submitted"
    assert out["result"] == "UPID:pve:00020:0:0:0:cephosddestroy:0:root@pam:"
    assert api.ceph_osd_destroys == [(1, None, True)]

    entry = _confirmed_entry(log, "pve_ceph_osd_destroy", "submitted")
    assert entry["mutation"] is True
    assert entry["detail"]["osdid"] == 1
    assert entry["detail"]["cleanup"] is True
    assert entry["detail"]["confirmed"] is True


def test_osd_destroy_osdid_zero_forwarded_exactly(tmp_path, monkeypatch):
    """The falsy-id lesson: osdid=0 must reach the wire call as 0, never dropped/defaulted."""
    _, api, _, log = _wire(tmp_path, monkeypatch)

    out = server.pve_ceph_osd_destroy(osdid=0, confirm=True)

    assert out["status"] == "submitted"
    assert api.ceph_osd_destroys == [(0, None, None)]
    entry = _confirmed_entry(log, "pve_ceph_osd_destroy", "submitted")
    assert entry["detail"]["osdid"] == 0
    assert entry["target"] == "pve/ceph/osd/0"


def test_osd_in_confirm_executes_forwards_exact_payload_and_records(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)

    out = server.pve_ceph_osd_in(osdid=1, confirm=True)

    assert out["status"] == "ok"
    assert out["status"] != "submitted"
    assert out["result"] is None
    assert api.ceph_osd_ins == [(1, None)]

    entry = _confirmed_entry(log, "pve_ceph_osd_in", "ok")
    assert entry["mutation"] is True
    assert entry["detail"]["osdid"] == 1
    assert entry["detail"]["confirmed"] is True


def test_osd_in_confirm_reports_submitted_if_a_upid_ever_comes_back(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    monkeypatch.setattr(api, "ceph_osd_in", lambda *a, **kw: "UPID:pve:surprise:0:0:0:cephosdin:0:root@pam:")

    out = server.pve_ceph_osd_in(osdid=0, confirm=True)

    assert out["status"] == "submitted"
    assert out["result"] == "UPID:pve:surprise:0:0:0:cephosdin:0:root@pam:"
    entry = _confirmed_entry(log, "pve_ceph_osd_in", "submitted")
    assert entry["mutation"] is True


def test_osd_out_confirm_executes_forwards_exact_payload_and_records(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)

    out = server.pve_ceph_osd_out(osdid=1, confirm=True)

    assert out["status"] == "ok"
    assert out["status"] != "submitted"
    assert out["result"] is None
    assert api.ceph_osd_outs == [(1, None)]

    entry = _confirmed_entry(log, "pve_ceph_osd_out", "ok")
    assert entry["mutation"] is True
    assert entry["detail"]["osdid"] == 1
    assert entry["detail"]["confirmed"] is True


def test_osd_scrub_confirm_executes_forwards_exact_payload_and_records(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)

    out = server.pve_ceph_osd_scrub(osdid=1, deep=True, confirm=True)

    assert out["status"] == "ok"
    assert out["status"] != "submitted"
    assert out["result"] is None
    assert api.ceph_osd_scrubs == [(1, None, True)]

    entry = _confirmed_entry(log, "pve_ceph_osd_scrub", "ok")
    assert entry["mutation"] is True
    assert entry["detail"]["osdid"] == 1
    assert entry["detail"]["deep"] is True
    assert entry["detail"]["confirmed"] is True


def test_osd_scrub_confirm_reports_submitted_if_a_upid_ever_comes_back(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    monkeypatch.setattr(
        api, "ceph_osd_scrub", lambda *a, **kw: "UPID:pve:surprise:0:0:0:cephosdscrub:0:root@pam:"
    )

    out = server.pve_ceph_osd_scrub(osdid=0, confirm=True)

    assert out["status"] == "submitted"
    entry = _confirmed_entry(log, "pve_ceph_osd_scrub", "submitted")
    assert entry["mutation"] is True


@pytest.mark.parametrize(
    "tool_name,kwargs",
    [
        ("pve_ceph_osd_create", {"dev": "/dev/sdb"}),
        ("pve_ceph_osd_destroy", {"osdid": 0}),
        ("pve_ceph_osd_in", {"osdid": 0}),
        ("pve_ceph_osd_out", {"osdid": 0}),
        ("pve_ceph_osd_scrub", {"osdid": 0}),
    ],
)
def test_wave_6c_confirm_true_never_returns_plan_status(tmp_path, monkeypatch, tool_name, kwargs):
    """Cross-check (table-driven, matching the sibling confirm-sweep files' style): every Wave
    6c ceph mutation's confirm=True path returns something other than "plan"."""
    _wire(tmp_path, monkeypatch)
    fn = getattr(server, tool_name)
    out = fn(confirm=True, **kwargs)
    assert out["status"] != "plan"


def test_wave_6c_one_shot_confirm_records_plan_before_executing(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    server.pve_ceph_osd_destroy(osdid=0, confirm=True)
    outcomes = {e["outcome"] for e in _entries(log) if e["action"] == "pve_ceph_osd_destroy"}
    assert "planned" in outcomes, "one-shot confirm must record a plan entry before executing"
    assert "submitted" in outcomes


# ---------------------------------------------------------------------------
# Wave 6d — pools + CephFS (CLOSES Wave 6). Same three-weld proof per mutation: executed shape,
# exact forwarded payload via the fake's typed method, and a confirmed ledger entry.
# ---------------------------------------------------------------------------


def test_pool_create_confirm_executes_forwards_exact_payload_and_records(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)

    out = server.pve_ceph_pool_create(
        name="newpool", application="rbd", crush_rule="replicated_rule", min_size=2,
        pg_autoscale_mode="on", pg_num=64, size=3, confirm=True,
    )

    assert out["status"] == "submitted"
    assert out["result"] == "UPID:pve:00021:0:0:0:cephpoolcreate:0:root@pam:"
    assert api.ceph_pool_creates == [(
        "newpool", None, None, "rbd", "replicated_rule", None, 2, "on", 64, None, 3, None, None,
    )]

    entry = _confirmed_entry(log, "pve_ceph_pool_create", "submitted")
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True
    assert entry["detail"]["name"] == "newpool"
    assert entry["detail"]["application"] == "rbd"
    assert entry["detail"]["pg_num"] == 64
    assert entry["detail"]["size"] == 3


def test_pool_create_minimal_call_forwards_none_for_omitted_optionals(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    server.pve_ceph_pool_create(name="newpool", confirm=True)
    assert api.ceph_pool_creates == [
        ("newpool", None, None, None, None, None, None, None, None, None, None, None, None)
    ]


def test_pool_create_erasure_coding_forwarded_exactly(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    out = server.pve_ceph_pool_create(name="ecpool", erasure_coding="k=2,m=1", confirm=True)
    assert out["status"] == "submitted"
    assert api.ceph_pool_creates[-1][5] == "k=2,m=1"
    entry = _confirmed_entry(log, "pve_ceph_pool_create", "submitted")
    assert entry["detail"]["erasure_coding"] == "k=2,m=1"


def test_pool_set_confirm_executes_forwards_exact_payload_and_records(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)

    out = server.pve_ceph_pool_set(name="rbd", size=3, pg_num=256, confirm=True)

    assert out["status"] == "submitted"
    assert out["result"] == "UPID:pve:00022:0:0:0:cephpoolset:0:root@pam:"
    assert api.ceph_pool_sets == [
        ("rbd", None, None, None, None, None, 256, None, 3, None, None)
    ]

    entry = _confirmed_entry(log, "pve_ceph_pool_set", "submitted")
    assert entry["mutation"] is True
    assert entry["detail"]["confirmed"] is True
    assert entry["detail"]["name"] == "rbd"
    assert entry["detail"]["pg_num"] == 256
    assert entry["detail"]["size"] == 3


def test_pool_set_zero_fields_refused_no_wire_call(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    with pytest.raises(ProximoError, match="requires at least one field"):
        server.pve_ceph_pool_set(name="rbd", confirm=True)
    assert api.ceph_pool_sets == []


def test_pool_destroy_confirm_executes_forwards_exact_payload_and_records(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)

    out = server.pve_ceph_pool_destroy(name="rbd", remove_storages=True, confirm=True)

    assert out["status"] == "submitted"
    assert out["result"] == "UPID:pve:00023:0:0:0:cephpooldestroy:0:root@pam:"
    assert api.ceph_pool_destroys == [("rbd", None, None, None, True)]

    entry = _confirmed_entry(log, "pve_ceph_pool_destroy", "submitted")
    assert entry["mutation"] is True
    assert entry["detail"]["name"] == "rbd"
    assert entry["detail"]["remove_storages"] is True
    assert entry["detail"]["confirmed"] is True


def test_pool_destroy_force_never_defaulted_on(tmp_path, monkeypatch):
    """force must reach the wire as None unless the caller explicitly sets it — never silently
    forwarded True."""
    _, api, _, log = _wire(tmp_path, monkeypatch)
    server.pve_ceph_pool_destroy(name="rbd", confirm=True)
    assert api.ceph_pool_destroys == [("rbd", None, None, None, None)]
    entry = _confirmed_entry(log, "pve_ceph_pool_destroy", "submitted")
    assert entry["detail"]["force"] is None


def test_pool_destroy_force_forwarded_when_explicitly_set(tmp_path, monkeypatch):
    _, api, _, _ = _wire(tmp_path, monkeypatch)
    server.pve_ceph_pool_destroy(name="rbd", force=True, confirm=True)
    assert api.ceph_pool_destroys == [("rbd", None, True, None, None)]


def test_fs_create_confirm_executes_forwards_exact_payload_and_records(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)

    out = server.pve_ceph_fs_create(name="myfs", add_storage=True, pg_num=64, confirm=True)

    assert out["status"] == "submitted"
    assert out["result"] == "UPID:pve:00024:0:0:0:cephfscreate:0:root@pam:"
    assert api.ceph_fs_creates == [(None, "myfs", True, 64)]

    entry = _confirmed_entry(log, "pve_ceph_fs_create", "submitted")
    assert entry["mutation"] is True
    assert entry["detail"]["name"] == "myfs"
    assert entry["detail"]["add_storage"] is True
    assert entry["detail"]["pg_num"] == 64
    assert entry["detail"]["confirmed"] is True


def test_fs_create_defaults_name_to_cephfs_on_the_wire(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    server.pve_ceph_fs_create(confirm=True)
    # the wrapper forwards the RAW None through to api.ceph_fs_create — the backend/plan layer
    # resolves the 'cephfs' literal default, not the wrapper (mirrors mon_create's own
    # "defaults resolved downstream, not at the wrapper" precedent, Wave 6b).
    assert api.ceph_fs_creates == [(None, None, None, None)]
    entry = _confirmed_entry(log, "pve_ceph_fs_create", "submitted")
    assert entry["detail"]["name"] == "cephfs"


def test_fs_destroy_confirm_executes_forwards_exact_payload_and_records(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)

    out = server.pve_ceph_fs_destroy(
        name="cephfs", remove_pools=True, remove_storages=True, confirm=True,
    )

    assert out["status"] == "submitted"
    assert out["result"] == "UPID:pve:00025:0:0:0:cephfsdestroy:0:root@pam:"
    assert api.ceph_fs_destroys == [("cephfs", None, True, True)]

    entry = _confirmed_entry(log, "pve_ceph_fs_destroy", "submitted")
    assert entry["mutation"] is True
    assert entry["detail"]["name"] == "cephfs"
    assert entry["detail"]["remove_pools"] is True
    assert entry["detail"]["remove_storages"] is True
    assert entry["detail"]["confirmed"] is True


@pytest.mark.parametrize(
    "tool_name,kwargs",
    [
        ("pve_ceph_pool_create", {"name": "newpool"}),
        ("pve_ceph_pool_set", {"name": "rbd", "size": 3}),
        ("pve_ceph_pool_destroy", {"name": "rbd"}),
        ("pve_ceph_fs_create", {}),
        ("pve_ceph_fs_destroy", {"name": "cephfs"}),
    ],
)
def test_wave_6d_confirm_true_never_returns_plan_status(tmp_path, monkeypatch, tool_name, kwargs):
    """Cross-check (table-driven, matching the sibling confirm-sweep files' style): every Wave
    6d ceph mutation's confirm=True path returns something other than "plan"."""
    _wire(tmp_path, monkeypatch)
    fn = getattr(server, tool_name)
    out = fn(confirm=True, **kwargs)
    assert out["status"] != "plan"


def test_wave_6d_one_shot_confirm_records_plan_before_executing(tmp_path, monkeypatch):
    _, api, _, log = _wire(tmp_path, monkeypatch)
    server.pve_ceph_pool_destroy(name="rbd", confirm=True)
    outcomes = {e["outcome"] for e in _entries(log) if e["action"] == "pve_ceph_pool_destroy"}
    assert "planned" in outcomes, "one-shot confirm must record a plan entry before executing"
    assert "submitted" in outcomes
