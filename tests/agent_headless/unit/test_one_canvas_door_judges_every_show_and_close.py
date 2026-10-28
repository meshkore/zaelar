"""One canvas door: every show and close crosses `nucleo.acts.canvas.apply`, judged by the ARMED arbiter (refactor2710-04 T-02).

A vetoed act never reaches the canvas and the door says so — its caller does not record it as done. An allowed act is
the `widget` event the canvas obeys, with its provenance, and its verdict is on the stream armed (`shadow: false`,
with `verdict` and `source`). Ops the arbiter does not license (minimize, fullscreen, move) cross the same door as they
are. The sheet of an errand the turn reopened belongs to that errand (`recall:<card>`), not to the model's words.
"""
from __future__ import annotations

import pytest

from nucleo import canvas_arbiter as arb
from nucleo.acts import canvas

NOTHING = {"text": "mm, vale", "turn_credit": True, "last_reply": "", "verdict": {}}


@pytest.fixture
def stream(monkeypatch):
    import voice.observer as obs
    out = []
    monkeypatch.setattr(obs, "emit", lambda kind, label, text="", role="", extra=None:
                        out.append((kind, label, dict(extra or {}))))
    return out


def _sink(out):
    return lambda kind, label, extra=None, **k: out.append((kind, label, dict(extra or {})))


def test_a_vetoed_show_never_reaches_the_canvas_and_the_door_says_so(stream):
    widget = []
    assert canvas.apply("show", "agenda", src="flash", request=NOTHING, emit=_sink(widget)) is False
    assert widget == [], "a veto must not put the card on screen"
    v = [e for e in stream if e[0] == "arbiter"][-1]
    assert v[2]["allow"] is False and v[2]["shadow"] is False and v[2]["source"] == "flash"


def test_an_ordered_close_reaches_the_canvas_with_its_provenance(stream):
    widget = []
    req = {**NOTHING, "verdict": {"canvas": ("close", 0.9)}}
    assert canvas.apply("close", "musica", src="flash", request=req, emit=_sink(widget)) is True
    assert widget == [("widget", "close", {"id": "musica", "src": "flash"})]
    v = [e for e in stream if e[0] == "arbiter"][-1]
    assert v[1] == "✅ permitida · verdict-close" and v[2]["verdict"] == {"canvas": {"choice": "close", "confidence": 0.9}}


def test_a_close_of_everything_has_no_id_and_ops_the_tree_does_not_license_pass_as_they_are(stream):
    widget = []
    assert canvas.apply("close", "", src="flash", request={**NOTHING, "verdict": {"canvas": ("close", 0.9)}},
                        emit=_sink(widget)) is True
    assert widget[-1] == ("widget", "close", {"src": "flash"}), "a close with no id is the canvas's close-all"
    assert canvas.apply("minimize", "agenda", src="flash", request=NOTHING, emit=_sink(widget)) is True
    assert widget[-1][1] == "minimize"


def test_the_sheet_of_a_reopened_errand_is_that_errands(stream):
    widget = []
    assert canvas.apply("show", "results::g", src="recall:results::g", request=NOTHING, emit=_sink(widget)) is True
    assert widget[-1][2]["src"] == "recall:results::g"


def test_the_door_does_not_judge_twice(stream):
    """The shadow tap hears the event the door emits; it must not file a second verdict for it."""
    canvas.apply("close", "musica", src="flash", request={**NOTHING, "verdict": {"canvas": ("close", 0.9)}})
    assert len([e for e in stream if e[0] == "arbiter"]) == 1


def test_disarm_a_door_that_skips_the_arbiter_lets_the_unlicensed_show_through(monkeypatch, stream):
    monkeypatch.setattr(canvas, "JUDGED", ())
    widget = []
    assert canvas.apply("show", "agenda", src="flash", request=NOTHING, emit=_sink(widget)) is True
    assert widget, "the disarm did not land"


def test_a_report_of_what_the_screen_did_is_recorded_even_when_the_tree_would_veto_it(stream):
    widget = []
    assert canvas.apply("close", "agenda", src="client:console", request=NOTHING, emit=_sink(widget)) is True
    assert widget and [e for e in stream if e[0] == "arbiter"][-1][2]["allow"] is False, "judged, recorded, not held"


# ── the door is the ONLY writer: no product code emits a canvas op around it ──────────────────────────────────

_OPS = {"show", "close", "minimize", "fullscreen", "move", "arrange"}
#: Writers whose label is computed and is not a canvas op (with what they emit).
_NOT_OPS = {"nucleo/flash/canvas_visibility.py": "the refusals of a show («presentación suprimida»)",
            "widgets/lifecycle.py": "delete / restore of a widget, after its confirm gate",
            "widgets/confirm.py": "the confirm prompt and its cancel",
            "nucleo/flash/data_ops.py": "a corrected data-op's diagnosis",
            "nucleo/flash/tool_executor_widget_calls.py": "the data-op log `data:<action>`",
            "widgets/rows.py": "a rows op's audit line",
            "widgets/server_api.py": "the generator's audit line"}


def _scan(rel: str, source: str) -> list[str]:
    import ast
    out = []
    for n in ast.walk(ast.parse(source)):
        if not (isinstance(n, ast.Call) and len(n.args) >= 2 and isinstance(n.args[0], ast.Constant)
                and n.args[0].value == "widget"):
            continue
        name = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
        if name not in ("emit", "_emit", "_say"):
            continue
        label = n.args[1]
        if isinstance(label, ast.Constant) and label.value in _OPS:
            out.append(f"{rel}:{n.lineno} {label.value}")
        elif not isinstance(label, ast.Constant) and rel not in _NOT_OPS:
            out.append(f"{rel}:{n.lineno} <computed label>")
    return out


def _writers_around_the_door() -> list[str]:
    from pathlib import Path
    engine = Path(__file__).resolve().parents[3]
    out = []
    for root in ("nucleo", "voice", "server", "widgets", "connectors"):
        for p in (engine / root).rglob("*.py"):
            rel = p.relative_to(engine).as_posix()
            if rel != "nucleo/acts/canvas.py" and "/_user/" not in rel:
                out += _scan(rel, p.read_text(encoding="utf-8"))
    return out


def test_every_canvas_op_crosses_the_one_door():
    assert not _writers_around_the_door(), "these write the canvas around nucleo.acts.canvas.apply: " + \
        "; ".join(_writers_around_the_door())


def test_disarm_a_bare_write_is_named():
    bare = 'from voice.observer import emit\nemit("widget", "show", extra={"id": "agenda"})\nemit("widget", op)\n'
    assert _scan("nucleo/x.py", bare) == ["nucleo/x.py:2 show", "nucleo/x.py:3 <computed label>"]


def test_a_broken_arbiter_fails_open_with_its_verdict_on_record(monkeypatch, stream):
    monkeypatch.setattr(arb, "_decide", lambda *a, **k: 1 / 0)
    widget = []
    assert canvas.apply("show", "agenda", src="flash", request=NOTHING, emit=_sink(widget)) is True
    assert [e for e in stream if e[0] == "arbiter"][-1][2]["rule"] == "arbiter-error"
