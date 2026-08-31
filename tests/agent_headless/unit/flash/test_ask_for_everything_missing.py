"""V2-149 (`reorder-prescription__es`) — four turns asking WHERE and not a single one asking WHAT.

The request was “ask for a refill of my prescription.” zaelar spent turns 1 through 4 locating the pharmacy — one
item at a time: name, then city, then the supermarket, then the street — and **never asked which prescription to
refill**, even though that is the object of the request. In turn 5: “perfect, that is enough for me… I’ll call to
ask for a refill of your prescription,” without knowing which one. The judge marks it `alta` twice and the watchdog
four times.

Two symmetrical rules from the one that has existed since V2-120 (if you are asked two things, answer both): ask
for both halves of what is missing in the same sentence, and do not consider a request complete while its OBJECT
remains unidentified.

The other half of the case was already fixed and is pinned here so it is not lost: the request already routes to
`web` (V2-144, `local_business`), so the task has a browser — and narrating “it has been locating the pharmacy for
about 70 seconds” for a task with no page open was fixed by V2-145. Both landed AFTER this run.
"""
from __future__ import annotations

import pytest

from nucleo import dispatch
from nucleo.flash import prompt
from nucleo.flash import router_guards as g
from nucleo.flash import site_catalog as sc


ASK = "Pide la reposición de mi receta de la farmacia de siempre."


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    from memory import db as memdb
    from memory import embeddings as mememb
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    mememb.reset()
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()
    mememb.reset()


def test_ask_for_everything_that_is_missing_at_once(fresh_db):
    system, _ = prompt.build_flash_system()
    assert "Pídelos TODOS de una vez" in system
    assert "no uno por turno" in system


def test_and_do_not_start_an_errand_whose_object_is_unknown(fresh_db):
    system, _ = prompt.build_flash_system()
    assert "comprueba que sabes QUÉ te ha encargado" in system
    assert "sin saber QUÉ receta" in system


def test_asking_is_still_the_correct_answer(fresh_db):
    """The rule sharpens HOW to ask, it does not discourage asking — this suite scores asking well (V2-082)."""
    system, _ = prompt.build_flash_system()
    assert "PÍDELO — preguntar es la respuesta" in system


# ── already-fixed behavior, pinned so it is not lost ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("text", [
    ASK,
    "pide la reposición de mi receta en la farmacia del barrio",
    "llama a la farmacia y pide la reposición de mi receta",
    "busca la farmacia al lado del Día en Bravo Murillo, Chamberí",
])
def test_the_errand_gets_a_browser(text):
    """V2-144: without a category, this was `generic` — a worker without a browser, which is why the task could not
exist. The `widget` family that the report found missing hangs off this."""
    assert sc.category_of(text) == "local_business"
    assert dispatch._classify_kind(text) == "web"
    assert g._needs_real_work(text) is True


def test_and_the_brain_cannot_narrate_a_browser_that_opened_nothing(fresh_db, monkeypatch):
    """V2-145: “it has been locating the pharmacy for about 70 seconds” for a task with an empty `url=`.

V2-152 changed the WORDING, not the guarantee: an empty record is described as “has not reported yet” (which is
true about what we know) instead of “has not opened any page” (a claim about the world that the record does not
support). What this test protects — not narrating what it would be doing — remains the same.
    """
    from widgets.navegador import tasks as nt
    monkeypatch.setattr(nt, "active_summaries", lambda limit=3: [("t9", "localizar la farmacia de Chamberí")])
    monkeypatch.setattr(nt, "active_progress",
                        lambda limit=3: [{"id": "t9", "goal": "x", "url": "", "phase": "", "steps": 0,
                                          "awaiting_login": False}])
    line = next(l for l in prompt.live_state().splitlines() if l.startswith("NAVEGADOR"))
    assert "AÚN NO HA REPORTADO NINGÚN PASO" in line
    assert "NO describas lo que estaría haciendo" in line


# ── V2-158: asking and launching are MUTUALLY EXCLUSIVE ──────────────────────────────────────────────────────
#
# `reorder-prescription__es` scored 5 for naturalness, adaptation, and outcome — the spoken behavior is exactly what
# the case calls for, because this request CANNOT be completed without data the operator does not have. And the
# MECHANISM scored 1: in turn 1, in addition to asking for the two data points, a browser task was launched whose
# objective was the operator's RAW TEXT. Without a pharmacy or medication name there is nothing to drive, so the
# task remained `status=working`, `url=''`, `events=[]` for all eight turns: the report claimed work was underway
# while the conversation correctly said it could not be started.
#
# The rule is deliberately in the prompt rather than in a deterministic guard: what must be decided is whether the
# request NAMES a concrete objective (“the usual pharmacy,” “the blood-pressure one” do not), and that is a
# semantic judgment — in this repo a model judges it, not a pattern (V2-075).
def test_asking_for_the_missing_datum_excludes_launching_the_task(fresh_db):
    system, _ = prompt.build_flash_system()
    assert "NO lances la tarea en ese mismo turno" in system
    assert "Pregunta AHORA y arranca CUANDO te contesten" in system


def test_and_it_says_why_a_task_without_the_datum_is_worse_than_none(fresh_db):
    """Without the reason, the rule reads as bureaucracy and the model skips it as soon as it is in a hurry."""
    system, _ = prompt.build_flash_system()
    assert "no hay nada que conducir" in system
    assert "diciendo que trabajas mientras preguntas" in system


def test_but_asking_is_still_the_right_answer(fresh_db):
    """The case scores ASKING as correct behavior. The new rule must not be read as “do not ask.”"""
    system, _ = prompt.build_flash_system()
    assert "PÍDELO — preguntar es la respuesta" in system
    assert "no un fallo" in system
