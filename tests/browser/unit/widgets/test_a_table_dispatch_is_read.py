"""The widget contract gate reads an `ACTIONS = {name: handler}` table (V2-778 F1-12, 2026-10-01).

F1-12 turns the widgets' `apply_action` if-chains into a table, and the gate had a blind spot exactly there: a
dispatch it could not parse statically FAIL-OPENED — no literal compared against the parameter meant an empty
set, and an empty set meant «don't judge». So moving a widget to a table would have switched its contract
check off without a sound: a declared action nobody handles, or a handled one the brain cannot see, would both
pass. The gate now reads the table's keys as the handled names.
"""
from __future__ import annotations

from widgets import validator

_DATA = '''def _a_play(action, p):
    return {"ok": True}


def _a_stop(action, p):
    return {"ok": True}


ACTIONS = {
    "play": _a_play,
    "pause": _a_play,
    "stop": _a_stop,
}


def apply_action(action, payload=None):
    h = ACTIONS.get(action)
    if h is None:
        return {"ok": False, "error": "unknown_action", "action": action}
    return h(action, payload or {})
'''


def _man(*names):
    return {"id": "w", "actions": {n: {"desc": "x"} for n in names}}


def test_the_table_keys_are_the_handled_actions():
    assert validator._apply_action_names(_DATA) == {"play", "pause", "stop"}
    assert validator._validate_actions_sync(_man("play", "pause", "stop"), _DATA) is None


def test_a_declared_action_the_table_lacks_is_dead():
    err = validator._validate_actions_sync(_man("play", "pause", "stop", "ghost"), _DATA)
    assert err and "ghost" in err, err


def test_a_table_entry_the_manifest_lacks_is_invisible():
    err = validator._validate_actions_sync(_man("play", "pause"), _DATA)
    assert err and "stop" in err, err


def test_a_table_apply_action_does_not_read_is_not_counted():
    """Only a table `apply_action` actually consults: a module-level dict it never names is not its dispatch."""
    src = _DATA.replace("h = ACTIONS.get(action)", "h = None")
    assert validator._apply_action_names(src) == set()
