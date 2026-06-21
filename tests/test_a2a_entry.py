"""The proximo-a2a console script ships in the base wheel; without the [a2a] extra it must
print an install hint, not a raw ModuleNotFoundError traceback."""
import builtins

import pytest

import proximo._a2a_entry as entry


@pytest.mark.parametrize("missing", ["a2a", "uvicorn"])
def test_friendly_exit_when_extra_module_missing(monkeypatch, capsys, missing):
    """Every top-level module the [a2a] extra provides gets the hint — uvicorn matters because
    app.main() imports it lazily; the shim probes it at import time."""
    real_import = builtins.__import__

    def missing_module(name, *args, **kwargs):
        if name == missing or name.startswith(missing + ".") or (
                missing == "a2a" and name == "proximo.a2a.app"):
            raise ModuleNotFoundError(f"No module named '{missing}'", name=missing)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing_module)
    with pytest.raises(SystemExit) as ei:
        entry.main()
    assert ei.value.code == 2
    err = capsys.readouterr().err
    assert 'pip install "proximo-proxmox[a2a]"' in err
    assert f"'{missing}'" in err


def test_reraises_when_name_is_none(monkeypatch):
    """A ModuleNotFoundError carrying no module name re-raises — fail toward noise, not the hint."""
    real_import = builtins.__import__

    def nameless_failure(name, *args, **kwargs):
        if name == "proximo.a2a.app":
            raise ModuleNotFoundError("import machinery failure")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", nameless_failure)
    with pytest.raises(ModuleNotFoundError):
        entry.main()


def test_delegates_to_a2a_main_when_installed(monkeypatch):
    called = []
    import proximo.a2a.app as app
    monkeypatch.setattr(app, "main", lambda: called.append(True))
    entry.main()
    assert called == [True]


def test_reraises_when_missing_module_is_not_the_extra(monkeypatch):
    """A missing SUBmodule (package installed but broken) must traceback, not hide behind the hint."""
    real_import = builtins.__import__

    def broken_a2a(name, *args, **kwargs):
        if name == "proximo.a2a.app" or name == "a2a" or name.startswith("a2a."):
            raise ModuleNotFoundError("No module named 'a2a._core'", name="a2a._core")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", broken_a2a)
    with pytest.raises(ModuleNotFoundError):
        entry.main()
