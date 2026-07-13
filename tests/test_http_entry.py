"""The proximo-http console script ships in the base wheel; without the [http] extra it must
print an install hint, not a raw ModuleNotFoundError traceback."""
import builtins

import pytest

import proximo._http_entry as entry


@pytest.mark.parametrize("missing", ["starlette", "uvicorn"])
def test_friendly_exit_when_extra_module_missing(monkeypatch, capsys, missing):
    """Every top-level module the [http] extra provides gets the hint — uvicorn matters because
    httpface.main() imports it lazily; the shim probes it at import time."""
    real_import = builtins.__import__

    def missing_module(name, *args, **kwargs):
        if name == missing or name.startswith(missing + "."):
            raise ModuleNotFoundError(f"No module named '{missing}'", name=missing)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing_module)
    with pytest.raises(SystemExit) as ei:
        entry.main()
    assert ei.value.code == 2
    err = capsys.readouterr().err
    assert 'pip install "proximo-proxmox[http]"' in err
    assert f"'{missing}'" in err


def test_delegates_to_httpface_main_when_installed(monkeypatch):
    called = []
    import proximo.httpface as httpface
    monkeypatch.setattr(httpface, "main", lambda: called.append(True))
    entry.main()
    assert called == [True]


def test_reraises_when_missing_module_is_not_the_extra(monkeypatch):
    """A missing SUBmodule (package installed but broken) must traceback, not hide behind the hint."""
    real_import = builtins.__import__

    def broken_starlette(name, *args, **kwargs):
        if name == "starlette" or name.startswith("starlette."):
            raise ModuleNotFoundError("No module named 'starlette._core'", name="starlette._core")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", broken_starlette)
    with pytest.raises(ModuleNotFoundError):
        entry.main()
