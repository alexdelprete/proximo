"""Shared pytest fixtures for the Proximo suite."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _no_real_proximo_env_file(tmp_path_factory):
    """Never let ``load_env_file()`` source the OPERATOR'S real ``~/.config/proximo/proximo.env``
    during tests. It is invoked by ``server.main()`` / ``proximo-a2a`` (exercised by
    ``test_main_module`` / ``test_doctor`` / ``test_a2a_entry``); on a real deployment box that file
    exists and carries this box's ``PROXIMO_*`` settings (e.g. ``PROXIMO_ENABLE_EXEC``), which would
    leak into ``os.environ`` and pollute every later test's config warnings.

    Point ``PROXIMO_ENV_FILE`` at a guaranteed-absent path. Managed via ``os.environ`` directly (NOT
    ``monkeypatch``) so this autouse fixture doesn't pull ``monkeypatch`` into every test's fixture
    graph and reorder it relative to other autouse fixtures. Tests that need a fixture env file
    override this with their own ``monkeypatch.setenv``."""
    absent = str(tmp_path_factory.getbasetemp() / "no_such_proximo.env")
    prev = os.environ.get("PROXIMO_ENV_FILE")
    os.environ["PROXIMO_ENV_FILE"] = absent
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop("PROXIMO_ENV_FILE", None)
        else:
            os.environ["PROXIMO_ENV_FILE"] = prev
