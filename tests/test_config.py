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
