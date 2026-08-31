"""What may become a TASK, and what may not (V2-118 round 2, 2026-08-18).

Two things the second run of `three-tasks-at-once` measured in the live task registry, both below the model:

  · Of the SEVEN tasks the registry recorded, THREE had «[SYSTEM] Brain worker · Task completed: …» as their
    goal — a worker spawned to "do" the previous worker's delivery message. Every escalation route has a
    fallback «if the model left `request` empty, use the turn text», and that text already carries the system
    note glued in front. Both channels keep an `operator_text` precisely to avoid this, and both say in their
    own comments that a note is «NEVER part of what the operator requested» — the fallbacks just never used it.

  · Not a single task of kind `code` appeared across FOURTEEN turns, while the turn said «I’ll load a platform game
    for you». `looks_like_create_widget` on that opening line is True and `_classify_kind` answers `code`,
    so nothing was ambiguous: the model simply called the tool once (for the report) and the widget request
    fell on the floor. The existing create-widget guard only fired when the turn had triggered NOTHING.
"""
from __future__ import annotations

from nucleo.flash import escalate, router_guards

_NOTE = "[SISTEMA] Brain worker · Tarea completada: No he podido encontrar monitores de segunda mano ≤150€"
_OPENING = ("Oye, tengo tres cosas. Hazme un informe sobre coches eléctricos para ciudad, búscame un monitor "
            "barato de segunda mano, y móntame un widget de un juego de plataformas tipo Super Mario.")


def test_a_system_note_is_stripped_from_a_task_goal():
    assert escalate.strip_system_notes(f"{_NOTE}\n\nVale, ¿qué tal lo llevas?") == "Vale, ¿qué tal lo llevas?"
    assert escalate.strip_system_notes(f"{_NOTE}\n[SISTEMA] otra\n\nhola") == "hola"


def test_a_turn_with_no_note_is_untouched():
    assert escalate.strip_system_notes(_OPENING) == _OPENING


def test_a_turn_that_is_ONLY_a_system_note_never_becomes_a_task(monkeypatch):
    """This is the worker-chasing-the-worker case: nothing the operator asked for is in there."""
    published: list = []
    monkeypatch.setattr(escalate, "_emit_bus", lambda topic, payload: published.append((topic, payload)))
    assert escalate.escalate_to_slowbrain(f"{_NOTE}\n") == 0
    assert published == []


def test_a_real_request_still_escalates_with_its_note_removed(monkeypatch):
    published: list = []
    monkeypatch.setattr(escalate, "_emit_bus", lambda topic, payload: published.append((topic, payload)))
    tid = escalate.escalate_to_slowbrain(f"{_NOTE}\n\nbúscame un monitor de segunda mano")
    assert tid > 0
    assert len(published) == 1
    topic, payload = published[0]
    assert topic == "escalate.requested"
    assert payload["request"] == "búscame un monitor de segunda mano"
    assert "[SISTEMA]" not in payload["request"]


# ── the create-widget guard gap ───────────────────────────────────────────────────────────────────────────
def test_the_opening_line_unambiguously_asks_to_build_a_widget():
    """If this were ambiguous, the backstop would be guesswork. It is not: the deterministic classifier says yes,
    and the dispatcher would send it to the generator."""
    from nucleo import dispatch
    assert router_guards.looks_like_create_widget(_OPENING) is True
    assert dispatch._classify_kind(_OPENING) == "code"


def test_the_three_requests_split_into_three_different_kinds():
    """What the case is meant to measure: REAL concurrency of distinct kinds. Each request on its own has its
    correct destination—the failure was never classification; it was that two of the three were never launched."""
    from nucleo import dispatch
    assert dispatch._classify_kind("Investiga y redacta un informe sobre coches eléctricos para ciudad") == "generic"
    assert dispatch._classify_kind("Busca en Wallapop monitores baratos de segunda mano") == "web"
    assert dispatch._classify_kind("Monta un widget de un juego de plataformas tipo Super Mario") == "code"


def test_a_request_that_already_covers_the_widget_needs_no_backstop():
    """The backstop only fills a gap: if the model has ALREADY requested the widget, it is not duplicated."""
    assert router_guards.looks_like_create_widget("Monta un widget de un juego de plataformas") is True
    assert router_guards.looks_like_create_widget("Investiga coches eléctricos para ciudad") is False


# ── V2-155: the backstop detected the widget and DEDUP swallowed it ──────────────────────────────────────
#
# 18:10 round on `three-tasks-at-once`: `max_concurrent=2`, `distinct_kinds=['web']`—the third task
# never existed, and zaelar ended up saying «I have no record of you requesting a game». The V2-118 backstop DID
# fire (`looks_like_create_widget(_OPENING)` is True, above). What it did was add the ENTIRE TURN as the
# request, and a turn that assigns three things contains the other two inside it: with «report» in the sentence,
# `dispatch._target_widget` assigns it destination `results`—the same as the report task—and `find_duplicate`
# discards it based on its STRONGEST signal, the same destination widget. It was detected and deduplicated against the
# task it was supposed to coexist with.
_GOAL_INFORME = ("Elaborar un informe detallado sobre coches eléctricos para ciudad: autonomía, precio, "
                 "tamaño compacto, facilidad de aparcamiento y carga.")


class _Live:
    def __init__(self, goal):
        self.goal, self.status = goal, "running"


def test_the_backstop_appends_only_the_clause_that_asks_for_the_widget():
    got = router_guards.create_widget_request(_OPENING)
    assert "Super Mario" in got
    assert "informe" not in got.lower()
    assert "monitor" not in got.lower()


def test_and_that_is_what_stops_the_report_from_swallowing_it(monkeypatch):
    """Proof that the trimming is not cosmetic: it is exactly what changes the dedup verdict.

    V2-158—the first version of this test read the REAL widget catalog through `_target_widget`, and a
    live run that creates a widget (`widgets/juego-plataformas-tipo/` appeared and disappeared during the
    run) changed the result: green with fixed ordering, red with random ordering. A regression test cannot
    depend on which widgets are on disk when it runs. The mapping MEASURED in the run is fixed—entire turn →
    `results`, game clause → no destination—and the only thing this fix changes is checked: the INPUT that
    `find_duplicate` receives."""
    from nucleo import dispatch
    measured = {_OPENING: "results", _GOAL_INFORME: "results"}
    monkeypatch.setattr(dispatch, "_target_widget", lambda t: measured.get(t, ""))
    monkeypatch.setattr(dispatch, "_SESSIONS", {"informe": _Live(_GOAL_INFORME)})
    assert dispatch.find_duplicate(_OPENING, "code") == "informe"              # what ran before
    assert dispatch.find_duplicate(router_guards.create_widget_request(_OPENING), "code") is None


def test_a_lone_widget_request_is_untouched():
    """Without separators there is nothing to trim: the existing behavior does not change."""
    assert router_guards.create_widget_request("móntame un widget de la bolsa") == "móntame un widget de la bolsa"


def test_and_a_turn_that_asks_for_no_widget_yields_nothing():
    assert router_guards.create_widget_request("búscame un monitor barato de segunda mano") == ""
    assert router_guards.create_widget_request("") == ""
