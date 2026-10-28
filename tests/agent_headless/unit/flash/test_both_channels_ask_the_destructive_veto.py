"""Node 2.492 — both channels ask ONE rule before a removal runs over a sure verdict (`destructive_veto.instead`).

A rule installed in one of two branches is half a fix (V2-252): the voice rail reaches it through
`verdict_card.takes_the_view`, the text channel through `verdict_card.retarget`, and each of those is called by its
channel before the model's call is dispatched.
"""
from __future__ import annotations

import ast
import pathlib

_FLASH = pathlib.Path(__file__).resolve().parents[4] / "nucleo" / "flash"


def _body(path: pathlib.Path, name: str) -> str:
    src = path.read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.get_source_segment(src, fn) or ""


def test_both_verdict_card_doors_call_the_veto_first():
    for name in ("takes_the_view", "retarget"):
        body = _body(_FLASH / "verdict_card.py", name)
        assert "_dv.instead(" in body, name
        assert body.index("_dv.instead(") < min(i for i in (body.find("_other_view("), body.find("forward_of(")) if i > 0), \
            f"{name}: the veto is asked before any other retarget"


def test_the_turn_reaches_its_door_before_dispatching():
    voice = (_FLASH / "tool_executor_widget_calls.py").read_text(encoding="utf-8")
    assert voice.index("_txw._vcard.takes_the_view(") < voice.index("_apply_widget_data(_cd[\"card\"], action_name, res.payload, ref)")
