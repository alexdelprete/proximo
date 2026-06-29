"""TDD tests for the node-lifecycle plane (Wave 4).

Covers:
- Validators: _check_disk, _check_backend, _check_storage_name, _check_timezone
- Plan factories: correct action/target/risk/blast wording for all mutation plans
- Destructive plan honesty: RISK_HIGH + "no undo"/"irreversible" + target name in blast_radius
- CAPTURE-or-declare: time/hosts/dns_set capture current state; complete=False when read fails
- Backend dispatcher: invalid backend rejected; per-backend required-param mismatch rejected
- Cert key redaction: "SENTINEL-PRIVKEY" appears in NO plan dict field and NO ledger line
  (both plan path and confirm path)
- Mutation gating: plan-by-default (no confirm → status=="plan"); confirm=True executes
- Bulk power: stopall is RISK_HIGH + fleet-wide; migrateall requires target + not-auto-reversible
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import proximo.server as server
from proximo.audit import AuditLedger
from proximo.backends import ProximoError
from proximo.config import ProximoConfig
from proximo.node_lifecycle import (
    _key_fingerprint,
    plan_node_cert_delete,
    plan_node_cert_upload,
    plan_node_disk_initgpt,
    plan_node_disk_wipe,
    plan_node_dns_set,
    plan_node_hosts_set,
    plan_node_migrateall,
    plan_node_startall,
    plan_node_stopall,
    plan_node_storage_backend_create,
    plan_node_storage_backend_delete,
    plan_node_time_set,
)

# ─── Constants ─────────────────────────────────────────────────────────────────

_KEY_SENTINEL = "SENTINEL-PRIVKEY"


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _make_cfg(log_path: str | None = None) -> ProximoConfig:
    return ProximoConfig(
        api_base_url="https://fake:8006/api2/json",
        node="pve",
        token_path="/dev/null",
        enable_agent=False,
        agent_allowlist=frozenset(),
        enable_exec=False,
        ct_allowlist=frozenset(),
        audit_log_path=log_path or "/dev/null",
        redact_ledger=False,
    )


class _FakeNodeApi:
    """Fake ApiBackend that records node-lifecycle calls and returns canned responses."""

    def __init__(
        self,
        *,
        time_result=None,
        hosts_result=None,
        dns_result=None,
        raise_time=False,
        raise_hosts=False,
        raise_dns=False,
    ):
        self.config = SimpleNamespace(node="pve")
        self.disk_wipes: list = []
        self.disk_initgpts: list = []
        self.storage_backend_creates: list = []
        self.storage_backend_deletes: list = []
        self.time_sets: list = []
        self.hosts_sets: list = []
        self.dns_sets: list = []
        self.cert_uploads: list = []
        self.cert_deletes: list = []
        self.startalls: list = []
        self.stopalls: list = []
        self.migratalls: list = []
        self._time_result = time_result or {"timezone": "UTC", "localtime": 0, "time": 0}
        self._hosts_result = hosts_result or {"data": "127.0.0.1 localhost\n", "digest": "abc123"}
        self._dns_result = dns_result or {"search": "lan", "dns1": "1.1.1.1"}
        self._raise_time = raise_time
        self._raise_hosts = raise_hosts
        self._raise_dns = raise_dns

    # --- reads ---
    def node_disks_list(self, node=None):
        return [{"devpath": "/dev/sda"}]

    def node_disk_smart(self, disk, node=None):
        return {"health": "PASSED"}

    def node_storage_backend_list(self, backend, node=None):
        return []

    def node_time_get(self, node=None):
        if self._raise_time:
            raise RuntimeError("cannot read time")
        return dict(self._time_result)

    def node_hosts_get(self, node=None):
        if self._raise_hosts:
            raise RuntimeError("cannot read hosts")
        return dict(self._hosts_result)

    def _get(self, path):
        if self._raise_dns:
            raise RuntimeError("cannot read dns")
        if "/dns" in path:
            return dict(self._dns_result)
        return {}

    # --- mutations ---
    def node_disk_wipe(self, disk, node=None):
        self.disk_wipes.append((disk, node))

    def node_disk_initgpt(self, disk, node=None):
        self.disk_initgpts.append((disk, node))
        return "UPID:initgpt"

    def node_storage_backend_create(self, backend, name, node=None, **kw):
        self.storage_backend_creates.append((backend, name, node, kw))
        return "UPID:create"

    def node_storage_backend_delete(self, backend, name, node=None, cleanup=False):
        self.storage_backend_deletes.append((backend, name, node, cleanup))
        return "UPID:delete"

    def node_time_set(self, timezone, node=None):
        self.time_sets.append((timezone, node))

    def node_hosts_set(self, data, node=None, digest=None):
        self.hosts_sets.append((data, node, digest))

    def node_dns_set(self, node=None, search=None, dns1=None, dns2=None, dns3=None):
        self.dns_sets.append((node, search, dns1, dns2, dns3))

    def node_cert_upload(self, certificates, node=None, key=None,
                         force=False, restart=False):
        # key arrives here on confirm=True — it must NOT reach the ledger
        self.cert_uploads.append((certificates, key, force, restart))
        return {"filename": "pem", "subject": "CN=test"}

    def node_cert_delete(self, node=None, restart=False):
        self.cert_deletes.append((node, restart))

    def node_startall(self, node=None, vms=None):
        self.startalls.append((node, vms))
        return "UPID:startall"

    def node_stopall(self, node=None, vms=None):
        self.stopalls.append((node, vms))
        return "UPID:stopall"

    def node_migrateall(self, target, node=None, vms=None, maxworkers=None):
        self.migratalls.append((target, node, vms, maxworkers))
        return "UPID:migrateall"


class _FakeExec:
    pass


def _wire_node(tmp_path, monkeypatch, *, api=None, **api_kw):
    """Wire server with a fake node-lifecycle API and a real ledger."""
    log = str(tmp_path / "audit.log")
    cfg = _make_cfg(log_path=log)
    node_api = api if api is not None else _FakeNodeApi(**api_kw)
    exec_ = _FakeExec()
    ledger = AuditLedger(log)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, node_api, exec_, ledger))
    return cfg, node_api, log


def _entries(log: str) -> list[dict]:
    with open(log, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# ─── Validators ────────────────────────────────────────────────────────────────

class TestCheckDisk:
    def test_valid_device(self):
        from proximo.backends import _check_disk
        assert _check_disk("/dev/sdb") == "/dev/sdb"
        assert _check_disk("/dev/nvme0n1") == "/dev/nvme0n1"

    def test_rejects_non_dev_path(self):
        from proximo.backends import _check_disk
        with pytest.raises(ProximoError, match="invalid disk device path"):
            _check_disk("/etc/passwd")

    def test_rejects_path_traversal(self):
        from proximo.backends import _check_disk
        with pytest.raises(ProximoError):
            _check_disk("/dev/../etc/passwd")

    def test_rejects_trailing_newline(self):
        from proximo.backends import _check_disk
        # \Z anchor: trailing newline must not slip through
        with pytest.raises(ProximoError):
            _check_disk("/dev/sdb\n")


class TestCheckBackend:
    def test_valid_backends(self):
        from proximo.backends import _check_backend
        for b in ("lvm", "lvmthin", "zfs", "directory"):
            assert _check_backend(b) == b

    def test_rejects_arbitrary(self):
        from proximo.backends import _check_backend
        with pytest.raises(ProximoError, match="unsupported storage backend"):
            _check_backend("btrfs")

    def test_rejects_trailing_newline(self):
        from proximo.backends import _check_backend
        with pytest.raises(ProximoError):
            _check_backend("lvm\n")


class TestCheckStorageName:
    def test_valid_name(self):
        from proximo.backends import _check_storage_name
        assert _check_storage_name("mypool") == "mypool"
        assert _check_storage_name("data-01") == "data-01"

    def test_rejects_leading_hyphen(self):
        from proximo.backends import _check_storage_name
        with pytest.raises(ProximoError, match="invalid storage name"):
            _check_storage_name("-bad")

    def test_rejects_trailing_newline(self):
        from proximo.backends import _check_storage_name
        with pytest.raises(ProximoError):
            _check_storage_name("pool\n")


class TestCheckTimezone:
    def test_valid_timezone(self):
        from proximo.backends import _check_timezone
        assert _check_timezone("America/Chicago") == "America/Chicago"
        assert _check_timezone("UTC") == "UTC"

    def test_rejects_control_chars(self):
        from proximo.backends import _check_timezone
        with pytest.raises(ProximoError, match="invalid timezone"):
            _check_timezone("UTC\x00bad")

    def test_rejects_trailing_newline(self):
        from proximo.backends import _check_timezone
        with pytest.raises(ProximoError):
            _check_timezone("UTC\n")


# ─── Key fingerprint ───────────────────────────────────────────────────────────

def test_key_fingerprint_is_redacted():
    fp = _key_fingerprint()
    assert fp == {"key": "[redacted]"}


# ─── Plan factories — Disks ────────────────────────────────────────────────────

class TestDiskWipePlan:
    def test_action_and_target(self):
        p = plan_node_disk_wipe("/dev/sdb")
        assert p.action == "pve_node_disk_wipe"
        assert "/dev/sdb" in p.target

    def test_risk_high(self):
        p = plan_node_disk_wipe("/dev/sdb")
        assert p.risk == "high"

    def test_irreversible_declaration(self):
        p = plan_node_disk_wipe("/dev/sdb")
        blast = " ".join(p.blast_radius)
        assert "no undo" in p.note.lower() or "irreversible" in p.note.lower()
        assert "/dev/sdb" in blast

    def test_destroys_all_data_wording(self):
        p = plan_node_disk_wipe("/dev/sdb")
        # must name the disk and declare destruction
        assert "DESTROYS" in p.change or "destroys" in p.change.lower()
        assert "/dev/sdb" in p.change

    def test_invalid_disk_raises(self):
        with pytest.raises(ProximoError):
            plan_node_disk_wipe("/etc/passwd")


class TestDiskInitGptPlan:
    def test_risk_high(self):
        p = plan_node_disk_initgpt("/dev/sdb")
        assert p.risk == "high"

    def test_names_disk_and_declares_irreversible(self):
        p = plan_node_disk_initgpt("/dev/sdb")
        combined = p.change + " ".join(p.blast_radius) + p.note
        assert "/dev/sdb" in combined
        assert "irreversible" in combined.lower() or "no undo" in combined.lower()


class TestStorageBackendCreatePlan:
    def test_zfs_valid(self):
        p = plan_node_storage_backend_create("zfs", "tank", devices="/dev/sdb", raidlevel="raidz")
        # HIGH: creating the backend FORMATS the disk — destroys pre-existing data immediately.
        assert p.risk == "high"
        assert "tank" in p.target
        combined = " ".join(p.blast_radius) + p.note
        assert "/dev/sdb" in combined and ("destroy" in combined.lower() or "format" in combined.lower())

    def test_zfs_missing_devices_raises(self):
        with pytest.raises(ProximoError, match="devices"):
            plan_node_storage_backend_create("zfs", "tank", raidlevel="raidz")

    def test_zfs_missing_raidlevel_raises(self):
        with pytest.raises(ProximoError, match="raidlevel"):
            plan_node_storage_backend_create("zfs", "tank", devices="/dev/sdb")

    def test_lvm_valid(self):
        p = plan_node_storage_backend_create("lvm", "vg0", devices="/dev/sdb")
        assert p.risk == "high"

    def test_lvm_raidlevel_rejected(self):
        with pytest.raises(ProximoError, match="raidlevel"):
            plan_node_storage_backend_create("lvm", "vg0", devices="/dev/sdb", raidlevel="raid1")

    def test_lvm_missing_devices_raises(self):
        with pytest.raises(ProximoError, match="devices"):
            plan_node_storage_backend_create("lvm", "vg0")

    def test_lvmthin_valid(self):
        p = plan_node_storage_backend_create("lvmthin", "thin", devices="/dev/sdb")
        assert p.risk == "high"

    def test_directory_valid(self):
        p = plan_node_storage_backend_create(
            "directory", "mydir", devices="/dev/sdc", filesystem="ext4"
        )
        assert p.risk == "high"

    def test_directory_missing_filesystem_raises(self):
        with pytest.raises(ProximoError, match="filesystem"):
            plan_node_storage_backend_create("directory", "mydir", devices="/dev/sdc")

    def test_directory_raidlevel_rejected(self):
        with pytest.raises(ProximoError, match="raidlevel"):
            plan_node_storage_backend_create(
                "directory", "mydir", devices="/dev/sdc", filesystem="ext4", raidlevel="single"
            )

    def test_invalid_backend_raises(self):
        with pytest.raises(ProximoError, match="unsupported storage backend"):
            plan_node_storage_backend_create("btrfs", "pool")

    # --- raidlevel type-safety (L13 fix) ----------------------------------------

    def test_zfs_raidlevel_bool_true_raises(self):
        """raidlevel=True is a bool, not a valid string — must be rejected for zfs.

        Bug: the old truthy check `if not kw.get("raidlevel")` accepted True
        because `not True == False`, then _form coerced it to integer 1 on the wire.
        """
        with pytest.raises(ProximoError, match="raidlevel"):
            plan_node_storage_backend_create(
                "zfs", "tank", devices="/dev/sdb", raidlevel=True
            )

    def test_zfs_raidlevel_int_raises(self):
        """raidlevel=1 (int) must be rejected — zfs requires a non-empty string."""
        with pytest.raises(ProximoError, match="raidlevel"):
            plan_node_storage_backend_create(
                "zfs", "tank", devices="/dev/sdb", raidlevel=1
            )

    def test_lvm_raidlevel_false_rejected(self):
        """raidlevel=False is non-None and must be rejected for lvm backends.

        Bug: the old truthy check `if kw.get("raidlevel")` accepted False
        (falsy) without raising, silently sending raidlevel=0 to PVE.
        """
        with pytest.raises(ProximoError, match="raidlevel"):
            plan_node_storage_backend_create(
                "lvm", "vg0", devices="/dev/sdb", raidlevel=False
            )

    def test_directory_raidlevel_false_rejected(self):
        """raidlevel=False is non-None and must be rejected for directory backend."""
        with pytest.raises(ProximoError, match="raidlevel"):
            plan_node_storage_backend_create(
                "directory", "mydir", devices="/dev/sdc", filesystem="ext4", raidlevel=False
            )


class TestStorageBackendDeletePlan:
    def test_zfs_blast_names_target_and_data(self):
        p = plan_node_storage_backend_delete("zfs", "tank")
        blast = " ".join(p.blast_radius)
        assert "tank" in blast
        assert "ALL data" in blast
        assert p.risk == "high"

    def test_lvm_blast_names_vg(self):
        p = plan_node_storage_backend_delete("lvm", "vg0")
        blast = " ".join(p.blast_radius)
        assert "vg0" in blast
        assert p.risk == "high"

    def test_directory_blast_wording(self):
        p = plan_node_storage_backend_delete("directory", "mydir")
        blast = " ".join(p.blast_radius)
        assert "mydir" in blast
        assert p.risk == "high"

    def test_no_undo_in_note(self):
        for backend in ("zfs", "lvm", "directory"):
            p = plan_node_storage_backend_delete(backend, "x")
            assert "no undo" in p.note.lower() or "irreversible" in p.note.lower()


# ─── Plan factories — CAPTURE-or-declare ──────────────────────────────────────

class TestCaptureTimeSet:
    def test_captures_current_timezone(self):
        api = _FakeNodeApi(time_result={"timezone": "America/Chicago"})
        p = plan_node_time_set(api, "UTC")
        assert p.complete is True
        assert p.current.get("timezone") == "America/Chicago"

    def test_complete_false_when_read_fails(self):
        api = _FakeNodeApi(raise_time=True)
        p = plan_node_time_set(api, "UTC")
        assert p.complete is False
        assert "could not capture" in p.note.lower()

    def test_risk_low(self):
        api = _FakeNodeApi()
        p = plan_node_time_set(api, "Europe/Berlin")
        assert p.risk == "low"

    def test_action(self):
        api = _FakeNodeApi()
        p = plan_node_time_set(api, "UTC")
        assert p.action == "pve_node_time_set"


class TestCaptureHostsSet:
    def test_captures_current_hosts(self):
        api = _FakeNodeApi(hosts_result={"data": "127.0.0.1 localhost\n", "digest": "d123"})
        p = plan_node_hosts_set(api, "127.0.0.1 newhost\n")
        assert p.complete is True
        assert "127.0.0.1 localhost" in p.current.get("data", "")

    def test_complete_false_when_read_fails(self):
        api = _FakeNodeApi(raise_hosts=True)
        p = plan_node_hosts_set(api, "127.0.0.1 newhost\n")
        assert p.complete is False
        assert "could not capture" in p.note.lower()

    def test_risk_medium(self):
        api = _FakeNodeApi()
        p = plan_node_hosts_set(api, "127.0.0.1 localhost\n")
        assert p.risk == "medium"


class TestCaptureDnsSet:
    def test_captures_current_dns(self):
        api = _FakeNodeApi(dns_result={"search": "lan", "dns1": "1.1.1.1"})
        p = plan_node_dns_set(api, dns1="8.8.8.8")
        assert p.complete is True
        assert p.current.get("dns1") == "1.1.1.1"

    def test_complete_false_when_read_fails(self):
        api = _FakeNodeApi(raise_dns=True)
        p = plan_node_dns_set(api, dns1="8.8.8.8")
        assert p.complete is False
        assert "could not capture" in p.note.lower()

    def test_risk_medium(self):
        # DNS resolver change can break name resolution cluster-wide — same failure mode as
        # hosts_set (MEDIUM), so dns_set is MEDIUM too, not LOW.
        api = _FakeNodeApi()
        p = plan_node_dns_set(api, search="local")
        assert p.risk == "medium"


# ─── Plan factories — Cert ────────────────────────────────────────────────────

class TestCertUploadPlan:
    def test_risk_high(self):
        p = plan_node_cert_upload("-----BEGIN CERT-----...")
        assert p.risk == "high"

    def test_lockout_warning_in_blast(self):
        p = plan_node_cert_upload("CERT", force=True)
        blast = " ".join(p.blast_radius)
        assert "lock you out" in blast or "lock" in blast.lower()

    def test_no_undo_in_note(self):
        p = plan_node_cert_upload("CERT")
        assert "no undo" in p.note.lower()

    def test_key_never_in_plan(self):
        # plan factory receives NO key param — the sentinel string can't appear
        p = plan_node_cert_upload("CERT")
        dump = json.dumps(p.as_dict())
        assert _KEY_SENTINEL not in dump


class TestCertDeletePlan:
    def test_risk_medium(self):
        p = plan_node_cert_delete()
        assert p.risk == "medium"

    def test_recoverable_in_note(self):
        # cert_delete is RECOVERABLE — must NOT say "no undo"
        p = plan_node_cert_delete()
        assert "recoverable" in p.note.lower()

    def test_self_signed_fallback_mentioned(self):
        p = plan_node_cert_delete()
        combined = p.change + p.note
        assert "self-signed" in combined.lower()


# ─── Plan factories — Bulk power ──────────────────────────────────────────────

class TestStartallPlan:
    def test_risk_medium(self):
        p = plan_node_startall()
        assert p.risk == "medium"

    def test_action(self):
        p = plan_node_startall()
        assert p.action == "pve_node_startall"

    def test_filtered_scope_in_change(self):
        p = plan_node_startall(vms="100,101")
        assert "100,101" in p.change or "100,101" in p.target


class TestStopallPlan:
    def test_risk_high(self):
        p = plan_node_stopall()
        assert p.risk == "high"

    def test_fleet_wide_in_blast(self):
        p = plan_node_stopall()
        blast = " ".join(p.blast_radius)
        assert "all" in blast.lower() and "guest" in blast.lower()

    def test_node_named_in_change(self):
        p = plan_node_stopall(node="pve1")
        assert "pve1" in p.change or "pve1" in p.target


class TestMigrateallPlan:
    def test_risk_high(self):
        p = plan_node_migrateall("pve2")
        assert p.risk == "high"

    def test_target_named(self):
        p = plan_node_migrateall("pve2")
        combined = p.change + p.note + " ".join(p.blast_radius)
        assert "pve2" in combined

    def test_not_auto_reversible(self):
        p = plan_node_migrateall("pve2")
        combined = p.change + p.note
        assert "not" in combined.lower() and "auto" in combined.lower()

    def test_invalid_target_raises(self):
        # space in node name is rejected by _check_node
        with pytest.raises(ProximoError):
            plan_node_migrateall("bad node!")  # space in name rejects


# ─── Cert key redaction — the PROVE check ─────────────────────────────────────

class TestCertKeyRedaction:
    """The private key MUST NEVER appear in any ledger line or plan dict field."""

    def test_key_not_in_plan_dict(self, tmp_path, monkeypatch):
        _wire_node(tmp_path, monkeypatch)
        out = server.pve_node_cert_upload("CERT-BODY", key=_KEY_SENTINEL)
        assert out["status"] == "plan"
        dump = json.dumps(out)
        assert _KEY_SENTINEL not in dump

    def test_key_not_in_ledger_plan_path(self, tmp_path, monkeypatch):
        _, _, log = _wire_node(tmp_path, monkeypatch)
        server.pve_node_cert_upload("CERT-BODY", key=_KEY_SENTINEL)
        with open(log) as f:
            leaks = [ln for ln in f if _KEY_SENTINEL in ln]
        assert leaks == [], f"key sentinel appeared in ledger (plan path): {leaks}"

    def test_key_not_in_ledger_confirm_path(self, tmp_path, monkeypatch):
        _, _, log = _wire_node(tmp_path, monkeypatch)
        server.pve_node_cert_upload("CERT-BODY", key=_KEY_SENTINEL, confirm=True)
        with open(log) as f:
            leaks = [ln for ln in f if _KEY_SENTINEL in ln]
        assert leaks == [], f"key sentinel appeared in ledger (confirm path): {leaks}"

    def test_cert_body_may_appear_in_plan(self, tmp_path, monkeypatch):
        """The cert body (public) is NOT redacted; it may appear in the plan."""
        _wire_node(tmp_path, monkeypatch)
        cert_body = "CERT-PUBLIC-BODY"
        out = server.pve_node_cert_upload(cert_body, key=_KEY_SENTINEL)
        # cert body (public) is allowed to appear in the plan output
        dump = json.dumps(out)
        assert cert_body in dump

    def test_key_redact_marker_in_plan_response(self, tmp_path, monkeypatch):
        """The [redacted] marker appears in the plan response for the key field."""
        _wire_node(tmp_path, monkeypatch)
        out = server.pve_node_cert_upload("CERT", key=_KEY_SENTINEL)
        assert out.get("key") == "[redacted]"


# ─── Mutation gating ──────────────────────────────────────────────────────────

class TestMutationGating:
    def test_disk_wipe_plan_by_default(self, tmp_path, monkeypatch):
        _, api, log = _wire_node(tmp_path, monkeypatch)
        out = server.pve_node_disk_wipe("/dev/sdb")
        assert out["status"] == "plan"
        assert api.disk_wipes == []  # nothing executed
        assert any(e["outcome"] == "planned" for e in _entries(log))

    def test_disk_wipe_confirm_executes(self, tmp_path, monkeypatch):
        _, api, log = _wire_node(tmp_path, monkeypatch)
        out = server.pve_node_disk_wipe("/dev/sdb", confirm=True)
        # async worker UPID — "submitted", never "ok" (the wipe is not done when the task is accepted)
        assert out["status"] == "submitted"
        assert len(api.disk_wipes) == 1
        outcomes = {e["outcome"] for e in _entries(log) if e["action"] == "pve_node_disk_wipe"}
        assert {"planned", "submitted"} <= outcomes

    def test_backend_delete_confirm_is_submitted(self, tmp_path, monkeypatch):
        # zpool/VG destroy is an async worker — must report "submitted", never "ok" (parity with create).
        _, api, log = _wire_node(tmp_path, monkeypatch)
        out = server.pve_node_storage_backend_delete("zfs", "tank", confirm=True)
        assert out["status"] == "submitted"
        assert len(api.storage_backend_deletes) == 1
        outcomes = {e["outcome"] for e in _entries(log)
                    if e["action"] == "pve_node_storage_backend_delete"}
        assert {"planned", "submitted"} <= outcomes

    def test_time_set_plan_by_default(self, tmp_path, monkeypatch):
        _, api, _ = _wire_node(tmp_path, monkeypatch)
        out = server.pve_node_time_set("UTC")
        assert out["status"] == "plan"
        assert api.time_sets == []

    def test_time_set_confirm_executes(self, tmp_path, monkeypatch):
        _, api, _ = _wire_node(tmp_path, monkeypatch)
        server.pve_node_time_set("Europe/Berlin", confirm=True)
        assert len(api.time_sets) == 1
        assert api.time_sets[0][0] == "Europe/Berlin"

    def test_stopall_plan_by_default(self, tmp_path, monkeypatch):
        _, api, _ = _wire_node(tmp_path, monkeypatch)
        out = server.pve_node_stopall()
        assert out["status"] == "plan"
        assert api.stopalls == []

    def test_stopall_confirm_executes(self, tmp_path, monkeypatch):
        _, api, _ = _wire_node(tmp_path, monkeypatch)
        out = server.pve_node_stopall(confirm=True)
        assert out["status"] == "submitted"
        assert len(api.stopalls) == 1

    def test_migrateall_plan_by_default(self, tmp_path, monkeypatch):
        _, api, _ = _wire_node(tmp_path, monkeypatch)
        out = server.pve_node_migrateall("pve2")
        assert out["status"] == "plan"
        assert api.migratalls == []

    def test_migrateall_confirm_executes(self, tmp_path, monkeypatch):
        _, api, _ = _wire_node(tmp_path, monkeypatch)
        out = server.pve_node_migrateall("pve2", confirm=True)
        assert out["status"] == "submitted"
        assert api.migratalls[0][0] == "pve2"

    def test_hosts_set_plan_by_default(self, tmp_path, monkeypatch):
        _, api, _ = _wire_node(tmp_path, monkeypatch)
        out = server.pve_node_hosts_set("127.0.0.1 myhost\n")
        assert out["status"] == "plan"
        assert api.hosts_sets == []

    def test_dns_set_plan_by_default(self, tmp_path, monkeypatch):
        _, api, _ = _wire_node(tmp_path, monkeypatch)
        out = server.pve_node_dns_set(dns1="8.8.8.8")
        assert out["status"] == "plan"
        assert api.dns_sets == []

    def test_cert_delete_plan_by_default(self, tmp_path, monkeypatch):
        _, api, _ = _wire_node(tmp_path, monkeypatch)
        out = server.pve_node_cert_delete()
        assert out["status"] == "plan"
        assert api.cert_deletes == []

    def test_cert_delete_confirm_executes(self, tmp_path, monkeypatch):
        _, api, _ = _wire_node(tmp_path, monkeypatch)
        out = server.pve_node_cert_delete(confirm=True)
        assert out["status"] == "ok"
        assert len(api.cert_deletes) == 1


# ─── One-shot confirm also records a plan first ───────────────────────────────

def test_one_shot_confirm_records_plan_before_executing(tmp_path, monkeypatch):
    _, api, log = _wire_node(tmp_path, monkeypatch)
    server.pve_node_disk_initgpt("/dev/sdb", confirm=True)
    outcomes = {e["outcome"] for e in _entries(log)
                if e["action"] == "pve_node_disk_initgpt"}
    assert "planned" in outcomes, "one-shot confirm must record a plan entry before executing"
    assert "submitted" in outcomes


# ─── Read tools ───────────────────────────────────────────────────────────────

class TestReadTools:
    def test_disks_list_returns_data(self, tmp_path, monkeypatch):
        _wire_node(tmp_path, monkeypatch)
        result = server.pve_node_disks_list()
        assert isinstance(result, list)

    def test_disk_smart_returns_data(self, tmp_path, monkeypatch):
        _wire_node(tmp_path, monkeypatch)
        result = server.pve_node_disk_smart("/dev/sda")
        assert isinstance(result, dict)

    def test_storage_backend_list_returns_list(self, tmp_path, monkeypatch):
        _wire_node(tmp_path, monkeypatch)
        result = server.pve_node_storage_backend_list("lvm")
        assert isinstance(result, list)

    def test_time_get_returns_dict(self, tmp_path, monkeypatch):
        _wire_node(tmp_path, monkeypatch)
        result = server.pve_node_time_get()
        assert isinstance(result, dict)

    def test_hosts_get_returns_dict(self, tmp_path, monkeypatch):
        _wire_node(tmp_path, monkeypatch)
        result = server.pve_node_hosts_get()
        assert isinstance(result, dict)
