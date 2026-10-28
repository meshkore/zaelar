"""A patch the bank puts on never outlives the bank, not even in a module imported while it was on (refactor2710-99, debt #101).

The bank swaps `fast_client.FastClient` for `RecordedModel` and puts it back on exit. A module imported for the first
time INSIDE a case and written `from nucleo.llm.fast_client import FastClient` bound the recorded stand-in under its own
name, and restoring the attribute on `fast_client` never reached that copy: five tests went red only in wide runs
(`_client_for` missing). On exit the real object goes back wherever the fake is still bound under the patched name.
"""
from __future__ import annotations

import sys
import types

from nucleo.llm import fast_client
from tests.brain import harness as H

_MOD = "tests_brain_bank_leak_probe"


def _enter_patch_import_exit(monkeypatch=None):
    real = fast_client.FastClient
    iso = H.Isolated("en")
    iso._set(fast_client, "FastClient", H.RecordedModel)
    probe = types.ModuleType(_MOD)
    probe.FastClient = fast_client.FastClient      # what `from nucleo.llm.fast_client import FastClient` binds
    sys.modules[_MOD] = probe
    iso.tmp = ""                                    # nothing else was entered
    iso.__exit__(None, None, None)
    return real, probe


def test_a_copy_bound_while_the_patch_was_on_gets_the_real_class_back():
    try:
        real, probe = _enter_patch_import_exit()
        assert fast_client.FastClient is real
        assert probe.FastClient is real, "the module imported during the case still holds the recorded model"
    finally:
        sys.modules.pop(_MOD, None)


def test_the_disarm_without_the_sweep_leaves_the_copy(monkeypatch):
    monkeypatch.setattr(H, "_unbind_copies", lambda *a, **k: None)
    try:
        real, probe = _enter_patch_import_exit()
        assert fast_client.FastClient is real
        assert probe.FastClient is H.RecordedModel, "with the sweep disarmed the leak is back — the test measures it"
    finally:
        sys.modules.pop(_MOD, None)
