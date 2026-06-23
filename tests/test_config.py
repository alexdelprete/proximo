"""Config tests — Proximo ships with tests from day one (the 'solid' principle)."""

import pytest

from proximo.config import ProximoConfig


def _cfg(**kw) -> ProximoConfig:
    base = dict(api_base_url="https://x:8006/api2/json", node="pve", token_path="/run/x")
    base.update(kw)
    return ProximoConfig(**base)


def test_allowlist_empty_denies_all():
    # Fail-closed: an unconfigured allowlist permits nothing.
    assert not _cfg().ct_permitted("999")


def test_allowlist_star_permits_all():
    assert _cfg(ct_allowlist=frozenset({"*"})).ct_permitted("12345")


def test_allowlist_gates_to_listed_ctids():
    c = _cfg(ct_allowlist=frozenset({"100"}))
    assert c.ct_permitted("100")
    assert not c.ct_permitted("200")


def test_is_local_detection():
    assert _cfg(ssh_target="local").is_local
    assert _cfg(ssh_target="").is_local
    assert not _cfg(ssh_target="pve").is_local


def test_from_env_fails_loud_when_core_missing(monkeypatch):
    for v in ("PROXIMO_API_BASE_URL", "PROXIMO_NODE", "PROXIMO_TOKEN_PATH"):
        monkeypatch.delenv(v, raising=False)
    with pytest.raises(RuntimeError):
        ProximoConfig.from_env()


def test_exec_is_off_by_default():
    # API-only is the safe default; in-container exec must be explicitly enabled.
    assert _cfg().enable_exec is False


def test_from_env_parses_enable_exec(monkeypatch):
    import warnings

    monkeypatch.setenv("PROXIMO_API_BASE_URL", "https://x:8006/api2/json")
    monkeypatch.setenv("PROXIMO_NODE", "pve")
    monkeypatch.setenv("PROXIMO_TOKEN_PATH", "/run/x")
    monkeypatch.setenv("PROXIMO_ENABLE_EXEC", "1")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        cfg = ProximoConfig.from_env()
    assert cfg.enable_exec is True


def test_verify_tls_defaults_to_true_when_unset(monkeypatch):
    # Fail-closed: TLS verification is ON unless explicitly disabled. (Guards against a silent flip.)
    monkeypatch.setenv("PROXIMO_API_BASE_URL", "https://x:8006/api2/json")
    monkeypatch.setenv("PROXIMO_NODE", "pve")
    monkeypatch.setenv("PROXIMO_TOKEN_PATH", "/run/x")
    monkeypatch.delenv("PROXIMO_VERIFY_TLS", raising=False)
    cfg = ProximoConfig.from_env()
    assert cfg.verify_tls is True


def test_verify_tls_false_without_ca_bundle_warns_loudly(monkeypatch):
    # Disabling verification with no CA bundle must not be silent.
    monkeypatch.setenv("PROXIMO_API_BASE_URL", "https://x:8006/api2/json")
    monkeypatch.setenv("PROXIMO_NODE", "pve")
    monkeypatch.setenv("PROXIMO_TOKEN_PATH", "/run/x")
    monkeypatch.setenv("PROXIMO_VERIFY_TLS", "false")
    monkeypatch.delenv("PROXIMO_CA_BUNDLE", raising=False)
    with pytest.warns(UserWarning, match="(?i)cert validation"):
        cfg = ProximoConfig.from_env()
    assert cfg.verify_tls is False


def test_redact_ledger_off_by_default():
    # Audit completeness is the default: ct_psql/ct_exec record the body unless explicitly opted out.
    assert _cfg().redact_ledger is False


def test_from_env_parses_redact_ledger(monkeypatch):
    import warnings

    monkeypatch.setenv("PROXIMO_API_BASE_URL", "https://x:8006/api2/json")
    monkeypatch.setenv("PROXIMO_NODE", "pve")
    monkeypatch.setenv("PROXIMO_TOKEN_PATH", "/run/x")
    monkeypatch.setenv("PROXIMO_LEDGER_REDACT", "1")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        cfg = ProximoConfig.from_env()
    assert cfg.redact_ledger is True


def _base_env(monkeypatch, **extra):
    monkeypatch.setenv("PROXIMO_API_BASE_URL", "https://x:8006/api2/json")
    monkeypatch.setenv("PROXIMO_NODE", "pve")
    monkeypatch.setenv("PROXIMO_TOKEN_PATH", "/run/x")
    for k, v in extra.items():
        monkeypatch.setenv(k, v)


def test_expected_head_defaults_none(monkeypatch):
    _base_env(monkeypatch)
    assert ProximoConfig.from_env().expected_head is None


def test_expected_head_accepts_64_hex(monkeypatch):
    h = "a" * 64
    _base_env(monkeypatch, PROXIMO_AUDIT_EXPECTED_HEAD=h)
    assert ProximoConfig.from_env().expected_head == h


def test_expected_head_rejects_malformed(monkeypatch):
    _base_env(monkeypatch, PROXIMO_AUDIT_EXPECTED_HEAD="not-a-hash")
    with pytest.raises(RuntimeError, match="PROXIMO_AUDIT_EXPECTED_HEAD"):
        ProximoConfig.from_env()


def test_audit_keyed_defaults_true(monkeypatch):
    _base_env(monkeypatch)
    assert ProximoConfig.from_env().audit_keyed is True


def test_audit_keyed_opt_out_off(monkeypatch):
    _base_env(monkeypatch, PROXIMO_AUDIT_KEYED="off")
    assert ProximoConfig.from_env().audit_keyed is False


def test_audit_keyed_opt_out_zero(monkeypatch):
    _base_env(monkeypatch, PROXIMO_AUDIT_KEYED="0")
    assert ProximoConfig.from_env().audit_keyed is False


def test_audit_keyed_on_stays_true(monkeypatch):
    _base_env(monkeypatch, PROXIMO_AUDIT_KEYED="on")
    assert ProximoConfig.from_env().audit_keyed is True
