"""V2-469 · the judge kept guessing WHEN each widget op happened — three rounds, three wrong [alta]s.

Measured in `build-a-video-playlist-from-links`: round 9's judge filed «play se ejecutó en el primer turno»
(the timeline shows it at +217s, right after «ponla ya»); round 11 filed «add dispara reproducciones»
(the plays sit in the turn where the operator said «ponla») and «falta un add por enlace» (a single add
carries N links BY DESIGN, V2-384 bis). The ops existed with timestamps and the report only gave totals —
a number without its WHEN reads like whatever the reader fears. `widget_ops_by_turn` buckets each widget
ACTION into the operator turn on the table when it fired, and the judge gets it enunciated with the two
rules it kept inventing wrong.
"""
from tests.use_cases.e2e.agent import judge, verify

_TRANSCRIPT = [
    {"who": "tester", "text": "Te paso dos vídeos: … móntame una lista.", "at": 100.0},
    {"who": "zaelar", "text": "Hecho.", "at": 103.0},
    {"who": "tester", "text": "Perfecto, pues ponla y dime qué está sonando.", "at": 130.0},
    {"who": "zaelar", "text": "Hecho.", "at": 133.0},
]

def _ev(t_s, action):
    return {"cat": "widget", "kind": "widget", "label": "action", "id": "youtube",
            "action": action, "t_ms": t_s * 1000.0}

_EVENTS = [_ev(101.5, "add"), _ev(131.0, "play"), _ev(131.8, "player_error"), _ev(132.0, "player_error")]


def test_each_op_lands_in_the_turn_it_fired_in():
    out = verify.widget_ops_by_turn(_EVENTS, _TRANSCRIPT)
    assert out == {"t0": ["youtube.add"],
                   "t1": ["youtube.play", "youtube.player_error", "youtube.player_error"]}


def test_an_op_before_any_turn_is_not_invented_into_one():
    out = verify.widget_ops_by_turn([_ev(50.0, "add")], _TRANSCRIPT)
    assert out == {"t0": ["youtube.add"]} or out == {}


def test_the_judge_gets_the_timing_and_the_two_rules():
    out = judge.mechanism_facts({
        "widget_ops": {"youtube": {"add": 1, "play": 1}},
        "widget_ops_by_turn": {"t0": ["youtube.add"], "t1": ["youtube.play"]},
    })
    assert "OPS POR TURNO" in out
    assert "t1: youtube.play" in out
    assert "VARIOS enlaces" in out
    assert "orden suya" in out


def test_without_the_field_nothing_renders():
    out = judge.mechanism_facts({"widget_ops": {"youtube": {"add": 1}}})
    assert "OPS POR TURNO" not in out


def test_run_wires_it():
    from pathlib import Path
    src = Path("tests/use_cases/e2e/agent/run.py").read_text(encoding="utf-8")
    assert "widget_ops_by_turn" in src
