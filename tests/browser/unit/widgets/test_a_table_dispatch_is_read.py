"""The widget contract gate reads an `ACTIONS = {name: handler}` table (V2-778 F1-12, 2026-10-01).

F1-12 turns the widgets' `apply_action` if-chains into a table, and the gate had a blind spot exactly there: a
dispatch it could not parse statically FAIL-OPENED — no literal compared against the parameter meant an empty
set, and an empty set meant «don't judge». So moving a widget to a table would have switched its contract
check off without a sound: a declared action nobody handles, or a handled one the brain cannot see, would both
pass. The gate now reads the table's keys as the handled names.
"""
from __future__ import annotations

from widgets import validator
from widgets import validator_actions as _validator_actions_m

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
    assert _validator_actions_m._apply_action_names(_DATA) == {"play", "pause", "stop"}
    assert _validator_actions_m._validate_actions_sync(_man("play", "pause", "stop"), _DATA) is None


def test_a_declared_action_the_table_lacks_is_dead():
    err = _validator_actions_m._validate_actions_sync(_man("play", "pause", "stop", "ghost"), _DATA)
    assert err and "ghost" in err, err


def test_a_table_entry_the_manifest_lacks_is_invisible():
    err = _validator_actions_m._validate_actions_sync(_man("play", "pause"), _DATA)
    assert err and "stop" in err, err


def test_a_table_apply_action_does_not_read_is_not_counted():
    """Only a table `apply_action` actually consults: a module-level dict it never names is not its dispatch."""
    src = _DATA.replace("h = ACTIONS.get(action)", "h = None")
    assert _validator_actions_m._apply_action_names(src) == set()


# refactor2710-12 — the table READ OFF the `_a_<action>` names: no list of action words written twice, and the gate
# still sees exactly what is handled.
_DERIVED = '''from .actions import _a_play, _shared


def _a_stop(action, p):
    return {"ok": True}


_a_pause = _a_rewind = _shared
ACTIONS = {name[3:]: fn for name, fn in list(globals().items()) if name.startswith("_a_")}


def apply_action(action, payload=None):
    h = ACTIONS.get(action)
    return h(action, payload or {}) if h else {"ok": False, "error": "unknown_action"}
'''


def test_a_table_read_off_the_handler_names_is_gated_both_ways():
    assert _validator_actions_m._apply_action_names(_DERIVED) == {"play", "stop", "pause", "rewind"}
    assert _validator_actions_m._validate_actions_sync(_man("play", "stop", "pause", "rewind"), _DERIVED) is None
    assert "ghost" in _validator_actions_m._validate_actions_sync(_man("play", "stop", "pause", "rewind", "ghost"), _DERIVED)
    assert "rewind" in _validator_actions_m._validate_actions_sync(_man("play", "stop", "pause"), _DERIVED)


def test_disarm_the_derived_table_fail_opens_without_its_reader(monkeypatch):
    monkeypatch.setattr(_validator_actions_m, "_bound_names", lambda tree: set())
    assert _validator_actions_m._validate_actions_sync(_man("play", "ghost"), _DERIVED) is None, "nothing read → fail-open"
