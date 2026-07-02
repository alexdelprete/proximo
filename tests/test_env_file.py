"""load_env_file() — source ~/.config/proximo/proximo.env into os.environ for the stdio launch.

Closes the config footgun where a PROXIMO_* var set in the documented proximo.env was silently
ignored by the stdio MCP server (fail-DANGEROUS for PROXIMO_CONSENT_DIR — see docs/known-issues.md).
Non-breaking: real/inline env always wins; only PROXIMO_* keys are touched; a missing file is a no-op.
"""

from __future__ import annotations

import os

import pytest

import proximo.config as config


@pytest.fixture(autouse=True)
def _clean_added_proximo_vars():
    """load_env_file mutates os.environ DIRECTLY (bypassing monkeypatch). Remove only the PROXIMO_*
    keys it adds during a test — never os.environ.clear() (which corrupts the shared suite) and
    never touch non-PROXIMO or pre-existing keys."""
    before = {k for k in os.environ if k.startswith("PROXIMO_")}
    yield
    for k in [k for k in os.environ if k.startswith("PROXIMO_") and k not in before]:
        os.environ.pop(k, None)


def _write_env(tmp_path, content: str) -> str:
    p = tmp_path / "proximo.env"
    p.write_text(content)
    return str(p)


def test_loads_unset_proximo_var_from_file(tmp_path, monkeypatch):
    monkeypatch.setenv("PROXIMO_ENV_FILE", _write_env(tmp_path, "PROXIMO_CONSENT_DIR=/srv/grants\n"))
    monkeypatch.delenv("PROXIMO_CONSENT_DIR", raising=False)
    loaded = config.load_env_file()
    assert loaded == ["PROXIMO_CONSENT_DIR"]
    assert os.environ["PROXIMO_CONSENT_DIR"] == "/srv/grants"


def test_real_env_wins_over_file(tmp_path, monkeypatch):
    """An already-set var (real env / inline mcpServers.env) is NEVER overridden by the file."""
    monkeypatch.setenv("PROXIMO_ENV_FILE", _write_env(tmp_path, "PROXIMO_CONSENT_DIR=/from/file\n"))
    monkeypatch.setenv("PROXIMO_CONSENT_DIR", "/from/inline")
    loaded = config.load_env_file()
    assert "PROXIMO_CONSENT_DIR" not in loaded
    assert os.environ["PROXIMO_CONSENT_DIR"] == "/from/inline"


def test_only_proximo_namespace_loaded_no_path_injection(tmp_path, monkeypatch):
    """A hostile/careless env file must NOT be able to inject non-PROXIMO_ vars (PATH, LD_*, ...)."""
    monkeypatch.setenv("PROXIMO_ENV_FILE",
                       _write_env(tmp_path, "PATH=/evil\nLD_PRELOAD=/x.so\nEVIL=1\nPROXIMO_NODE=pve\n"))
    monkeypatch.delenv("PROXIMO_NODE", raising=False)
    real_path = os.environ.get("PATH")
    loaded = config.load_env_file()
    assert loaded == ["PROXIMO_NODE"]
    assert os.environ.get("PATH") == real_path      # untouched
    assert "LD_PRELOAD" not in os.environ
    assert "EVIL" not in os.environ


def test_missing_file_is_noop(tmp_path, monkeypatch):
    monkeypatch.setenv("PROXIMO_ENV_FILE", str(tmp_path / "does-not-exist.env"))
    assert config.load_env_file() == []


def test_directory_path_is_noop(tmp_path, monkeypatch):
    """A path that is a directory (misconfig) => no-op, not a crash."""
    monkeypatch.setenv("PROXIMO_ENV_FILE", str(tmp_path))
    assert config.load_env_file() == []


def test_comments_blanks_export_and_quotes(tmp_path, monkeypatch):
    content = (
        "# a comment\n"
        "\n"
        "export PROXIMO_NODE=pve\n"
        "PROXIMO_TOKEN_PATH='/run/tok'\n"
        'PROXIMO_API_BASE_URL="https://x:8006/api2/json"\n'
        "  PROXIMO_CONSENT_TTL_SECONDS = 600 \n"
    )
    monkeypatch.setenv("PROXIMO_ENV_FILE", _write_env(tmp_path, content))
    for k in ("PROXIMO_NODE", "PROXIMO_TOKEN_PATH", "PROXIMO_API_BASE_URL", "PROXIMO_CONSENT_TTL_SECONDS"):
        monkeypatch.delenv(k, raising=False)
    config.load_env_file()
    assert os.environ["PROXIMO_NODE"] == "pve"
    assert os.environ["PROXIMO_TOKEN_PATH"] == "/run/tok"                      # single quotes stripped
    assert os.environ["PROXIMO_API_BASE_URL"] == "https://x:8006/api2/json"    # double quotes stripped
    assert os.environ["PROXIMO_CONSENT_TTL_SECONDS"] == "600"                  # surrounding ws stripped


def test_default_path_when_env_file_unset(tmp_path, monkeypatch):
    """With PROXIMO_ENV_FILE unset, the default ~/.config/proximo/proximo.env is used."""
    monkeypatch.delenv("PROXIMO_ENV_FILE", raising=False)
    cfgdir = tmp_path / ".config" / "proximo"
    cfgdir.mkdir(parents=True)
    (cfgdir / "proximo.env").write_text("PROXIMO_NODE=fromdefault\n")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("PROXIMO_NODE", raising=False)
    config.load_env_file()
    assert os.environ["PROXIMO_NODE"] == "fromdefault"


def test_consent_dir_from_file_now_reaches_environ(tmp_path, monkeypatch):
    """The reviewer's HIGH, closed: PROXIMO_CONSENT_DIR set in proximo.env now reaches os.environ, so
    CONSENT is no longer silently inert under stdio (the config warning + gate will activate)."""
    monkeypatch.setenv("PROXIMO_ENV_FILE", _write_env(tmp_path, "PROXIMO_CONSENT_DIR=/srv/grants\n"))
    monkeypatch.delenv("PROXIMO_CONSENT_DIR", raising=False)
    assert os.environ.get("PROXIMO_CONSENT_DIR") is None  # before: silently inert
    config.load_env_file()
    assert os.environ["PROXIMO_CONSENT_DIR"] == "/srv/grants"  # after: CONSENT activates
