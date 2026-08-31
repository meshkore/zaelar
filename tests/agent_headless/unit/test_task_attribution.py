"""V2-140 (`three-tasks-at-once`, tier 4) — criterion 2: an allusion must reach the RIGHT task.

The case's own words: «Responding for the wrong task, mixing two together, or swallowing a refinement without
acknowledging receipt is a SERIOUS failure. ASKING which one it refers to when it is genuinely ambiguous is NOT a
failure.»

Measured with the three live tasks and the case's real phrases, before touching anything:

    «and the one about the car?»              → ['t1','t2','t3']   (t1 IS «report on electric CARS»)
    «the monitor one, make it 27 inches»     → ['t1','t2','t3']   (t2 IS «a cheap second-hand MONITOR»)

Two mechanical causes, neither of them the model:

  · the punctuation stayed GLUED to the word — `car?`, `monitor,` — because the tokenizer split on whitespace
    over a `_norm` that only strips accents and lowercases. That is the SAME defect that cost real money in
    V2-123 (`find_duplicate` comparing «guitar» with «(guitar»), in its sibling function, in the same file,
    unreviewed at the time;
  · the crossing was exact-match, so `car` did not recognise `cars`. Alluding in the singular to something
    asked for in the plural is just how people talk.

What deliberately does NOT change: a genuinely ambiguous allusion still resolves to every live task. That
fallback is load-bearing for V2-123's merge design and has its own test right next to this one.
"""
from __future__ import annotations

import pytest

from nucleo import dispatch


THREE = [
    ("t1", "hazme un informe sobre coches eléctricos para ciudad", "research"),
    ("t2", "búscame un monitor barato de segunda mano", "web"),
    ("t3", "móntame un widget de un juego de plataformas tipo Super Mario", "code"),
]


@pytest.fixture
def three_live_tasks(monkeypatch):
    sessions = {}
    for tid, goal, kind in THREE:
        rec = dispatch.SessionRecord(task_id=tid, goal=goal, kind=kind)
        rec.status = "running"
        sessions[tid] = rec
    monkeypatch.setattr(dispatch, "_SESSIONS", sessions)
    return sessions


@pytest.mark.parametrize("allusion,expected", [
    ("¿y el del coche?", "t1"),                             # singular ↔ plural, and a glued «?»
    ("y el informe?", "t1"),
    ("el del monitor, que sea de 27 pulgadas", "t2"),       # a glued «,»
    ("el del juego", "t3"),
    ("el de las plataformas", "t3"),
])
def test_an_allusion_reaches_the_task_it_names(three_live_tasks, allusion, expected):
    assert dispatch.resolve_sessions(allusion) == [expected]


@pytest.mark.parametrize("allusion", [
    "ese ponle que salte más alto",     # nothing in it names a task — asking is the correct behaviour
    "oye",
    "para todo",
])
def test_a_genuinely_ambiguous_one_still_resolves_to_all(three_live_tasks, allusion):
    """Deliberate, and load-bearing: with several running and no unambiguous match, picking one is a guess —
    V2-123 rests on this and has its own test. Narrowing it is a design decision, not a bug fix."""
    assert dispatch.resolve_sessions(allusion) == ["t1", "t2", "t3"]


# ── the matching itself, at its two edges ───────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("a,b", [("coche", "coches"), ("informe", "informes"), ("monitor", "monitores"),
                                 ("juego", "juegos")])
def test_the_same_thing_said_singular_or_plural(a, b):
    assert dispatch._same_thing(a, b) is True


@pytest.mark.parametrize("a,b", [("coche", "cocina"), ("casa", "casamiento"), ("mono", "monitor")])
def test_but_a_shared_beginning_is_not_the_same_thing(a, b):
    """Bounded on purpose: attribution that guesses wrong sends the refinement to the task it is not, which is
    worse than not resolving. Minimum 4 characters of stem and at most 3 of difference."""
    assert dispatch._same_thing(a, b) is False


def test_punctuation_never_travels_glued_to_a_word():
    """The V2-123 defect, in its sibling function: «coche?» and «monitor,» could never match anything."""
    assert dispatch._ref_words("¿y el del coche?") == {"coche"}
    assert "monitor" in dispatch._ref_words("el del monitor, que sea de 27 pulgadas")
