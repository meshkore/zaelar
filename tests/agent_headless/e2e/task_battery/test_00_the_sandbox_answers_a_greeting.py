"""The battery's floor: a sandbox boots, answers one greeting, and its mechanism can be read (V2-851 F0).

Written and proved green BEFORE the twelve cases, so a red case is never the fixture's fault. It asserts only what
any version of the engine must do with «hello»: one turn, one trace, ONE line on the wall from the turn's own mouth,
and no task row — a greeting is a reflex, never a task.
"""
from __future__ import annotations

import pytest

GREETING = {"es": "Hola, ¿qué tal?", "en": "Hi, how are you?"}


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_greeting_is_one_line_and_no_task(probe_for, check, lang, rep):
    p = probe_for(lang)
    turn = p.say(GREETING[lang])
    lines = p.wait_for(lambda: p.lines(turn.trace), timeout=20, every=1) or []
    check.that("the flow is readable", bool(p.flow(turn.trace)), f"trace {turn.trace}")
    check.that("one line on the wall", len(lines) == 1, [(s, (e.get("label") or "")) for s, e in lines])
    check.that("the line is the turn's reply", [s for s, _ in lines] == ["reply"], [s for s, _ in lines])
    rows = [r for r in p.all_tasks() if str(r.get("trace_id") or "") == turn.trace]
    check.that("a greeting opens no visible task", not [r for r in rows if r.get("visible")], rows)
    check.done(expected_red=check.expected)
