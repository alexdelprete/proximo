"""Secret-file permission floor — EVERY secret referenced by path, not just PVE's.

SECURITY.md/README claim config "refuses a group/other-readable token file". Before the
2026-07-13 truth audit that was only true for the PVE token + audit HMAC key
(test_config.py covers those). These tests pin the same floor for the other planes'
credentials (PBS/PMG/PDM) and the network faces' bearer tokens + A2A signing key —
so the public claim is true for every secret Proximo reads by path.
"""
import pytest

from proximo import webguard
from proximo.pbs import PbsConfig
from proximo.pdm import PdmConfig
from proximo.pmg import PmgConfig


def _secret(tmp_path, name, mode, content="user@pam!id=s3cr3t\n"):
    p = tmp_path / name
    p.write_text(content)
    p.chmod(mode)
    return p


# --- PBS ------------------------------------------------------------------


def _pbs_env(monkeypatch, token_path):
    monkeypatch.setenv("PROXIMO_PBS_BASE_URL", "https://pbs.example.lan:8007/api2/json")
    monkeypatch.setenv("PROXIMO_PBS_TOKEN_PATH", str(token_path))


def test_pbs_world_readable_token_refused(monkeypatch, tmp_path):
    _pbs_env(monkeypatch, _secret(tmp_path, "pbs.token", 0o644))
    with pytest.raises(RuntimeError, match="chmod 600"):
        PbsConfig.from_env()


def test_pbs_owner_only_token_accepted(monkeypatch, tmp_path):
    tok = _secret(tmp_path, "pbs.token", 0o600)
    _pbs_env(monkeypatch, tok)
    assert PbsConfig.from_env().token_path == str(tok)


def test_pbs_missing_token_file_skips_perm_guard(monkeypatch, tmp_path):
    # Missing file already fails loudly at call time (run-but-not-read) — unchanged.
    _pbs_env(monkeypatch, tmp_path / "absent.token")
    PbsConfig.from_env()  # must not raise


def test_pbs_from_target_world_readable_token_refused(tmp_path):
    tok = _secret(tmp_path, "pbs.token", 0o644)
    with pytest.raises(RuntimeError, match="chmod 600"):
        PbsConfig.from_target({
            "base_url": "https://pbs.example.lan:8007/api2/json",
            "token_path": str(tok),
        })


# --- PMG ------------------------------------------------------------------


def _pmg_env(monkeypatch, password_path):
    monkeypatch.setenv("PROXIMO_PMG_BASE_URL", "https://pmg.example.lan:8006/api2/json")
    monkeypatch.setenv("PROXIMO_PMG_PASSWORD_PATH", str(password_path))


def test_pmg_world_readable_password_refused(monkeypatch, tmp_path):
    _pmg_env(monkeypatch, _secret(tmp_path, "pmg.pass", 0o644, "hunter-two\n"))
    with pytest.raises(RuntimeError, match="chmod 600"):
        PmgConfig.from_env()


def test_pmg_owner_only_password_accepted(monkeypatch, tmp_path):
    pw = _secret(tmp_path, "pmg.pass", 0o600, "hunter-two\n")
    _pmg_env(monkeypatch, pw)
    assert PmgConfig.from_env().password_path == str(pw)


def test_pmg_from_target_world_readable_password_refused(tmp_path):
    pw = _secret(tmp_path, "pmg.pass", 0o644, "hunter-two\n")
    with pytest.raises(RuntimeError, match="chmod 600"):
        PmgConfig.from_target({
            "base_url": "https://pmg.example.lan:8006/api2/json",
            "password_path": str(pw),
        })


# --- PDM ------------------------------------------------------------------


def _pdm_env(monkeypatch, token_path):
    monkeypatch.setenv("PROXIMO_PDM_BASE_URL", "https://pdm.example.com:8443")
    monkeypatch.setenv("PROXIMO_PDM_TOKEN_PATH", str(token_path))


def test_pdm_world_readable_token_refused(monkeypatch, tmp_path):
    _pdm_env(monkeypatch, _secret(tmp_path, "pdm.token", 0o644))
    with pytest.raises(RuntimeError, match="chmod 600"):
        PdmConfig.from_env()


def test_pdm_owner_only_token_accepted(monkeypatch, tmp_path):
    tok = _secret(tmp_path, "pdm.token", 0o600)
    _pdm_env(monkeypatch, tok)
    assert PdmConfig.from_env().token_path == str(tok)


def test_pdm_from_target_world_readable_token_refused(tmp_path):
    tok = _secret(tmp_path, "pdm.token", 0o644)
    with pytest.raises(RuntimeError, match="chmod 600"):
        PdmConfig.from_target({
            "base_url": "https://pdm.example.com:8443",
            "token_path": str(tok),
        })


# --- Network-face bearer tokens (A2A + HTTP share webguard.load_token_file) ----


def test_webguard_world_readable_bearer_token_refused(monkeypatch, tmp_path):
    tok = _secret(tmp_path, "face.token", 0o644, "bearer-tok\n")
    monkeypatch.setenv("PROXIMO_HTTP_TOKEN_FILE", str(tok))
    with pytest.raises(RuntimeError, match="chmod 600"):
        webguard.load_token_file("PROXIMO_HTTP_TOKEN_FILE")


def test_webguard_owner_only_bearer_token_accepted(monkeypatch, tmp_path):
    tok = _secret(tmp_path, "face.token", 0o600, "bearer-tok\n")
    monkeypatch.setenv("PROXIMO_A2A_TOKEN_FILE", str(tok))
    assert webguard.load_token_file("PROXIMO_A2A_TOKEN_FILE") == "bearer-tok"


def test_webguard_missing_token_file_still_fails_loud(monkeypatch, tmp_path):
    # Configured-but-missing must stay a LOUD failure (never silently unauthenticated).
    monkeypatch.setenv("PROXIMO_A2A_TOKEN_FILE", str(tmp_path / "absent"))
    with pytest.raises(RuntimeError, match="could not be read"):
        webguard.load_token_file("PROXIMO_A2A_TOKEN_FILE")


# --- A2A signing key ------------------------------------------------------


def test_a2a_world_readable_signing_key_refused(monkeypatch, tmp_path):
    from proximo.a2a import app as a2a_app
    key = _secret(tmp_path, "signing.pem", 0o644, "not-really-a-key\n")
    monkeypatch.setenv("PROXIMO_A2A_SIGNING_KEY_FILE", str(key))
    with pytest.raises(RuntimeError, match="chmod 600"):
        a2a_app._load_signing_key()
