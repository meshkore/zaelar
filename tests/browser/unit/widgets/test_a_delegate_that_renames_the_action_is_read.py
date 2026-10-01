"""The widget contract gate follows a delegate that renames its action parameter (V2-778 F1-12, 2026-10-01).

`make test-widgets` had been red on the agenda since V2-744: `apply_action` hands every task verb to
`tasklists.apply(action, …)`, and that function normalizes the name first — `act = str(action or "")` — then
compares `act`. The gate read only literals compared against the parameter itself, so thirteen declared actions
that DO run read as dead manifest entries. The gate now follows plain aliases inside a delegate.
"""
from __future__ import annotations

import json

from widgets import validator

_DATA = '''from . import sub


def apply_action(action, payload=None):
    if action == "own":
        return {"ok": True}
    if action in sub.ACTIONS:
        return sub.apply(action, payload or {})
    return {"ok": False}
'''
_SUB = '''ACTIONS = ("add_task", "done")


def apply(action, payload):
    act = str(action or "")
    if act == "add_task":
        return {"ok": True}
    if act == "done":
        return {"ok": True}
    return {"ok": False}
'''


def _widget(tmp_path):
    (tmp_path / "data.py").write_text(_DATA, encoding="utf-8")
    (tmp_path / "sub.py").write_text(_SUB, encoding="utf-8")
    return {"id": "w", "actions": {"own": {"desc": "x"}, "add_task": {"desc": "x"}, "done": {"desc": "x"}}}


def test_a_delegate_that_renames_its_parameter_counts_its_actions(tmp_path):
    man = _widget(tmp_path)
    assert validator._validate_actions_sync(man, _DATA, str(tmp_path)) is None


def test_a_declared_action_nobody_handles_is_still_dead(tmp_path):
    man = _widget(tmp_path)
    man["actions"]["ghost"] = {"desc": "x"}
    err = validator._validate_actions_sync(man, _DATA, str(tmp_path))
    assert err and "ghost" in err, err
