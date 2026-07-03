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


# --- The spine section: four pillars standing, two sockets yours to erect ---

def test_spine_reports_four_standing_pillars(monkeypatch):
    monkeypatch.delenv("PROXIMO_CONSENT_DIR", raising=False)
    monkeypatch.delenv("PROXIMO_CONTAIN_TRIP_PATH", raising=False)
    out = doctor_check(_DoctorApi())
    standing = " ".join(out["spine"]["standing"])
    for pillar in ("PLAN", "PROVE", "UNDO", "DIAGNOSE"):
        assert pillar in standing
    assert len(out["spine"]["standing"]) == 4


def test_spine_sockets_unconfigured_hand_over_the_tools(monkeypatch):
    """Unset CONSENT/CONTAIN must read as an empty socket WITH the erection recipe —
    surface the incompleteness and hand the operator the stone, never a false clean bill."""
    monkeypatch.delenv("PROXIMO_CONSENT_DIR", raising=False)
    monkeypatch.delenv("PROXIMO_CONTAIN_TRIP_PATH", raising=False)
    out = doctor_check(_DoctorApi())
    yours = out["spine"]["yours_to_erect"]
    for name, env in (("CONSENT", "PROXIMO_CONSENT_DIR"), ("CONTAIN", "PROXIMO_CONTAIN_TRIP_PATH")):
        assert yours[name]["configured"] is False
        assert env in yours[name]["erect_with"]
        assert "out" in yours[name]["erect_with"].lower()  # names the out-of-band requirement
    assert "outside" in out["spine"]["note"].lower()  # the note states the out-of-band doctrine


def test_spine_sockets_configured_report_standing(monkeypatch):
    monkeypatch.setenv("PROXIMO_CONSENT_DIR", "/run/operator/consent")
    monkeypatch.setenv("PROXIMO_CONTAIN_TRIP_PATH", "/run/operator/contain.trip")
    out = doctor_check(_DoctorApi())
    yours = out["spine"]["yours_to_erect"]
    assert yours["CONSENT"]["configured"] is True
    assert yours["CONTAIN"]["configured"] is True


def test_spine_carries_no_secret_material_and_no_socket_values(monkeypatch):
    """The spine section reports configured yes/no — never the configured PATHS themselves
    (a consent-dir/trip-path location is exactly what a hijacked session shouldn't learn
    from a doctor call; the operator knows where they put their own switch)."""
    monkeypatch.setenv("PROXIMO_CONSENT_DIR", "/run/operator/secret-consent-location")
    monkeypatch.setenv("PROXIMO_CONTAIN_TRIP_PATH", "/run/operator/secret-trip-location")
    out = doctor_check(_DoctorApi())
    rendered = json.dumps(out["spine"])
    assert "secret-consent-location" not in rendered
    assert "secret-trip-location" not in rendered


# --- No-secret-material invariant (CodeQL alert #75 guard) ---

def test_doctor_report_carries_no_secret_material(tmp_path):
    """`proximo doctor` prints its report as clear text (server.main json.dumps) — the report
    must never carry secret VALUES, even though the backend object it is built from has read
    them (that object-level flow is exactly what CodeQL py/clear-text-logging flags). Secrets
    stay by-reference (paths) end to end; this test pins that invariant with sentinels planted
    on every secret-bearing seam. Sentinels are low-entropy by design (gitleaks entropy rules)."""
    token_secret = "sentinel-doctor-token-secret-value"
    pmg_password = "sentinel-doctor-pmg-password-value"
    token_file = tmp_path / "token"
    token_file.write_text(f"root@pam!proximo={token_secret}\n")
    cfg = _cfg(token_path=str(token_file))
    api = _DoctorApi(config=cfg)
    # Simulate a backend that has ALREADY read its secrets — the taint source in the alert.
    api.auth_header = f"PVEAPIToken=root@pam!proximo={token_secret}"
    api.pmg_password = pmg_password

    rendered = json.dumps(doctor_check(api))  # exactly what the CLI prints

    assert token_secret not in rendered
    assert pmg_password not in rendered
    assert "PVEAPIToken" not in rendered
    assert token_file.read_text().strip() not in rendered
