"""A module faked in `sys.modules` is also what its package hands out, and both come back (refactor2710-99).

`from nucleo import mesh_agents` reads the PACKAGE attribute first: once any earlier test imported the real module, a
fake put only into `sys.modules` is shadowed, and the test that relied on it goes red only in a full run
(`test_the_mesh_cli_names_its_forms_when_misused` after `test_network_rows_never_open_a_sheet_for_a_report`). The root
conftest makes `monkeypatch.setitem(sys.modules, …)` set the parent's attribute too, and gives both back.

Disarm: remove the `self.setattr(pkg, child, …)` line in `conftest.py` and the first test goes red.
"""
from __future__ import annotations

import sys
import types

import pytest


def test_the_fake_is_what_from_import_gets_even_after_the_real_one_was_imported(monkeypatch):
    import nucleo.mesh_agents as real                 # the earlier test's import, made here so order never matters
    fake = types.SimpleNamespace(find=lambda *a, **k: "FAKE")
    monkeypatch.setitem(sys.modules, "nucleo.mesh_agents", fake)
    from nucleo import mesh_agents
    assert mesh_agents is fake and mesh_agents is not real


def test_both_come_back_when_the_test_ends():
    import nucleo
    import nucleo.mesh_agents as real
    mp = pytest.MonkeyPatch()
    mp.setitem(sys.modules, "nucleo.mesh_agents", types.SimpleNamespace())
    mp.undo()
    assert sys.modules["nucleo.mesh_agents"] is real and nucleo.mesh_agents is real
