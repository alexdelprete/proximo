"""`python -m proximo` is the MCP-client invocation the README documents — keep it wired.

Importing the module must NOT start the server (the start is guarded by
``if __name__ == "__main__"``); it must expose a callable ``main``.
"""
import importlib


def test_main_module_importable_and_wired():
    mod = importlib.import_module("proximo.__main__")
    assert callable(mod.main)
