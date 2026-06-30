"""`python -m proximo` is the MCP-client invocation the README documents — keep it wired.

Importing the module must NOT start the server (the start is guarded by
``if __name__ == "__main__"``); it must expose a callable ``main``.
"""
import importlib


def test_main_module_importable_and_wired():
    mod = importlib.import_module("proximo.__main__")
    assert callable(mod.main)


def test_main_doctor_subcommand_prints_json_and_skips_server(monkeypatch, capsys):
    # `proximo doctor` lets a user verify their token/config BEFORE wiring Proximo into any AI
    # client — it runs the read-only preflight and prints its JSON, and must NOT start the server.
    import json

    import proximo.server as srv

    monkeypatch.setattr(srv.sys, "argv", ["proximo", "doctor"])
    # stub matches the real (target-aware) pve_doctor signature: the CLI now passes proximo_target
    monkeypatch.setattr(srv, "pve_doctor", lambda proximo_target=None: {"reachable": True, "_marker": "DOCTORCLI"})
    ran = {"server": False}
    monkeypatch.setattr(srv.mcp, "run", lambda *a, **k: ran.__setitem__("server", True))

    srv.main()

    parsed = json.loads(capsys.readouterr().out)  # the ONLY thing on stdout must be the doctor JSON
    assert parsed["_marker"] == "DOCTORCLI"
    assert ran["server"] is False                 # doctor mode never starts the MCP server
