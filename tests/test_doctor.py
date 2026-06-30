"""pve_doctor — connectivity + token-permission preflight (unit + PROVE seam).

The doctor is read-only and onboarding-facing: it answers "is my config/token right, and what
can this token actually DO?" before a stranger wires Proximo into an MCP client. Same advisory,
never-overclaim posture as DIAGNOSE; routes through the ledger (mutation=False) like other reads.
"""
from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import proximo.server as server
from proximo import targets
from proximo.audit import AuditLedger
from proximo.config import ProximoConfig
from proximo.doctor import doctor_check


def _cfg(**kw):
    base = dict(node="pve", api_base_url="https://pve.example:8006/api2/json",
               enable_exec=False, verify_tls=True, ca_bundle=None, ct_allowlist=frozenset())
    base.update(kw)
    return SimpleNamespace(**base)


class _DoctorApi:
    def __init__(self, *, version=None, version_raises=False, perms=None, perms_raises=False, config=None):
        self._version = version if version is not None else {"release": "8.2", "version": "8.2.1"}
        self._version_raises = version_raises
        self._perms = perms if perms is not None else {"/": {"Sys.Audit": 1, "VM.Audit": 1}}
        self._perms_raises = perms_raises
        self.config = config or _cfg()

    def version(self):
        if self._version_raises:
            raise RuntimeError("connect timeout")
        return self._version

    def access_permissions(self, path=None):
        if self._perms_raises:
            raise RuntimeError("403 permission denied")
        return self._perms


def test_reachable_and_version():
    out = doctor_check(_DoctorApi())
    assert out["reachable"] is True
    assert out["version"].get("version") == "8.2.1"
    assert out["complete"] is True


def test_unreachable_flags_and_incomplete():
    out = doctor_check(_DoctorApi(version_raises=True))
    assert out["reachable"] is False
    assert any("reach" in f.lower() or "authenticat" in f.lower() for f in out["flags"])
    assert out["complete"] is False


def test_capability_can_when_priv_present():
    out = doctor_check(_DoctorApi(perms={"/": {"VM.Audit": 1, "VM.PowerMgmt": 1}}))
    cans = " ".join(c["capability"].lower() for c in out["token"]["can"])
    assert "power" in cans


def test_capability_cannot_has_needs_and_hint():
    out = doctor_check(_DoctorApi(perms={"/": {"VM.Audit": 1}}))  # read-only token, no power
    power = [c for c in out["token"]["cannot"] if "power" in c["capability"].lower()]
    assert power, "power should be in the cannot list for a read-only token"
    assert "VM.PowerMgmt" in " ".join(power[0]["needs"])
    assert power[0]["hint"] and "pveum acl modify" in power[0]["hint"]


def test_scoped_grant_is_noted_not_root():
    # snapshot only granted on a pool path, not at root — doctor must say it's scoped there.
    out = doctor_check(_DoctorApi(perms={"/": {"VM.Audit": 1}, "/pool/proximo-test": {"VM.Snapshot": 1}}))
    snap = [c for c in out["token"]["can"]
            if "snapshot" in c["capability"].lower() or "undo" in c["capability"].lower()]
    assert snap, "snapshot capability should be present (granted on the pool)"
    assert any("/pool/proximo-test" in s.get("scope", "") for s in snap)


def test_no_permissions_is_flagged():
    out = doctor_check(_DoctorApi(perms={}))
    assert any("no permission" in f.lower() or "cannot read or act" in f.lower() for f in out["flags"])


def test_perms_read_failure_is_flagged_not_crash():
    out = doctor_check(_DoctorApi(perms_raises=True))
    assert out["reachable"] is True  # version() still worked
    assert any("permission" in f.lower() for f in out["flags"])
    assert out["complete"] is False


def test_config_readiness_surfaced():
    out = doctor_check(_DoctorApi(config=_cfg(enable_exec=False, verify_tls=False, ca_bundle=None)))
    assert out["config"]["exec_enabled"] is False
    assert out["config"]["node"] == "pve"
    assert any("tls" in f.lower() for f in out["flags"])  # TLS off + no CA bundle warned


def test_rollback_not_overclaimed_without_rollback_priv():
    # VM.Snapshot (create) but NOT VM.Snapshot.Rollback — must NOT claim the UNDO/rollback works.
    out = doctor_check(_DoctorApi(perms={"/": {"VM.Audit": 1, "VM.Snapshot": 1}}))
    can = " ".join(c["capability"].lower() for c in out["token"]["can"])
    assert "create restore points" in can  # snapshot create IS available
    rollback_cannot = [c for c in out["token"]["cannot"] if "rollback" in c["capability"].lower()]
    assert rollback_cannot, "rollback must be in CANNOT without VM.Snapshot.Rollback"
    assert "VM.Snapshot.Rollback" in " ".join(rollback_cannot[0]["needs"])


def test_reconfigure_partial_is_labelled():
    # Only one VM.Config.* priv — capability is present but must be labelled partial, not full.
    out = doctor_check(_DoctorApi(perms={"/": {"VM.Config.Network": 1}}))
    recfg = [c for c in out["token"]["can"] if "reconfigure" in c["capability"].lower()]
    assert recfg and "partial" in recfg[0]["capability"].lower()
    assert "VM.Config.Network" in recfg[0]["capability"]


def test_users_and_acls_are_split():
    # Permissions.Modify (ACLs) does NOT imply User.Modify (users) — they're distinct powers.
    out = doctor_check(_DoctorApi(perms={"/": {"Permissions.Modify": 1}}))
    can = " ".join(c["capability"].lower() for c in out["token"]["can"])
    cannot = " ".join(c["capability"].lower() for c in out["token"]["cannot"])
    assert "tokens / acls" in can
    assert "manage users" in cannot


# --- seam: pve_doctor through the server records to the PROVE ledger as a read (mutation=False) ---

def test_pve_doctor_records_read_to_ledger(tmp_path, monkeypatch):
    log = str(tmp_path / "audit.log")
    cfg = ProximoConfig(api_base_url="https://x:8006/api2/json", node="pve", token_path="/run/x",
                        audit_log_path=log)
    api = _DoctorApi(config=cfg)  # api.config is a real ProximoConfig here
    ledger = AuditLedger(log)
    monkeypatch.setattr(server, "_svc", lambda: (cfg, api, None, ledger))

    out = server.pve_doctor()
    assert out["reachable"] is True
    with open(log, encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]
    assert any(e["action"] == "pve_doctor" and e["outcome"] == "ok" and e["mutation"] is False
               for e in entries)


# --- target routing: pve_doctor(proximo_target=...) sets the contextvar before _svc() fires ---
# This is a characterization test — target_aware already wraps pve_doctor, so it is GREEN today.
# It guards against regressions that would remove the target routing from this tool.

def test_pve_doctor_routes_to_named_target(monkeypatch):
    """pve_doctor(proximo_target="mybox") must set _active_target to "mybox" for the duration
    of the call — captured here via a patched _svc() that reads the contextvar."""
    captured = {}

    class _FakeLedger:
        def record(self, action, *, target, mutation=False, outcome="ok", detail=None, remote=None):
            return {}

    def _fake_svc():
        captured["target"] = targets._active_target.get()
        cfg = SimpleNamespace(node="pve", api_base_url="https://pve.example:8006/api2/json",
                              enable_exec=False, verify_tls=True, ca_bundle=None,
                              ct_allowlist=frozenset())
        api = _DoctorApi(config=cfg)
        return cfg, api, None, _FakeLedger()

    monkeypatch.setattr(server, "_svc", _fake_svc)
    server.pve_doctor(proximo_target="mybox")
    assert captured["target"] == "mybox"


def test_pve_doctor_default_target_is_none(monkeypatch):
    """Calling pve_doctor() with no proximo_target must leave _active_target as None (default path)."""
    captured = {}

    class _FakeLedger:
        def record(self, action, *, target, mutation=False, outcome="ok", detail=None, remote=None):
            return {}

    def _fake_svc():
        captured["target"] = targets._active_target.get()
        cfg = SimpleNamespace(node="pve", api_base_url="https://pve.example:8006/api2/json",
                              enable_exec=False, verify_tls=True, ca_bundle=None,
                              ct_allowlist=frozenset())
        api = _DoctorApi(config=cfg)
        return cfg, api, None, _FakeLedger()

    monkeypatch.setattr(server, "_svc", _fake_svc)
    server.pve_doctor()
    assert captured["target"] is None


# --- CLI: `proximo doctor --target <name>` passes proximo_target=<name> to pve_doctor ---

def test_cli_doctor_passes_target_to_pve_doctor(monkeypatch, capsys):
    """CLI: `proximo doctor --target mybox` must call pve_doctor(proximo_target="mybox").
    RED before the server.py change (current main() calls pve_doctor() with no args)."""
    called = {}

    def _stub(**kw):
        called.update(kw)
        return {}

    monkeypatch.setattr(server, "pve_doctor", _stub)
    monkeypatch.setattr(sys, "argv", ["proximo", "doctor", "--target", "mybox"])
    server.main()
    assert called.get("proximo_target") == "mybox"


def test_cli_doctor_no_target_defaults_to_none(monkeypatch, capsys):
    """CLI: `proximo doctor` (no --target) must call pve_doctor(proximo_target=None)."""
    called = {}

    def _stub(**kw):
        called.update(kw)
        return {}

    monkeypatch.setattr(server, "pve_doctor", _stub)
    monkeypatch.setattr(sys, "argv", ["proximo", "doctor"])
    server.main()
    assert called.get("proximo_target") is None
