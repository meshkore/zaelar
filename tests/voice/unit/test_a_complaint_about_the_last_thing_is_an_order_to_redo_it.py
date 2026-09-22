"""V2-752 — a correction of what we just did carries the licence of what it corrects.

THE INCIDENT (live session fce3eff3, 2026-09-22). He asked for Apollo videos, the STT heard «Apolón»,
and the player filled with videos from channels called Apolo. He corrected it twice, and both
corrections were RIGHT AT THE MODEL and eaten by a guard:

    +149.4 s  «He dicho, Apollo once.»                          → query="Apollo 11" → 🛡️ ignorado
    +164.9 s  «Yo sigo viendo en pantalla los mismos vídeos»     → query="Apollo 11" → 🛡️ ignorado

…each followed by `⚠️ promesa sin acción`: it said «Voy con Apollo 11 — te la saco» and did nothing.
It landed on the third attempt, when he finally put a media noun in the sentence. His own question
afterwards was «¿Cómo es posible que haya costado tanto llegar hasta aquí?».

Every reader involved was right about the sentence it was given. The grammar found no media verb (true:
a correction borrows its subject from the thing it corrects). `screen_action` answered `none` at 0.92
(true: read alone, that sentence asks for nothing). Nothing anywhere asked the question the situation
poses — is he telling me the last one was wrong? — and `🗣️ queja sobre lo ya hecho` fired FIVE times in
that session while being used only to suppress.

AND THE SECOND HALF, same session. The whisper auditor saw the promise with nothing behind it,
concluded correctly that a consequential action had failed, and escalated a full Claude Code worker to
run a YouTube search. It drove a real browser for four minutes, clicked into a video's comments, asked
twice for a widget called `videos` (the card is `youtube`), and delivered nothing. That is the
operator's standing complaint — «no es normal que para hacer una simple búsqueda de vídeos arranquemos
un brainworker» — arriving through a door V2-750 did not look at.

Run: .venv/bin/pytest tests/voice/unit/test_a_complaint_about_the_last_thing_is_an_order_to_redo_it.py
"""
from __future__ import annotations

import pytest

from nucleo import done_ops
from nucleo.flash import canvas_license, redo_decision, turn_brief


@pytest.fixture(autouse=True)
def _clean_ops():
    done_ops.reset()
    yield
    done_ops.reset()


def _brief(answers: dict):
    """A brief handle in the shape `turn_brief.read` consumes, already resolved."""
    import threading
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t", "open_ids": (),
            "result": {k: {"choice": v, "confidence": c, "probs": {}} for k, (v, c) in answers.items()}}


# ── 1 · THE QUESTION IS ONLY ASKED WHEN THERE IS SOMETHING IT COULD BE ABOUT ───────────────────────────
def test_a_cold_canvas_does_not_pay_for_this_question():
    """With nothing just done the answer could only be «unrelated», and a question whose answer is known
    does not earn its place in the brief."""
    assert redo_decision.question() is None
    assert redo_decision.REDO_KEY not in turn_brief.build("ponme el número seis")


def test_the_question_carries_what_we_ACTUALLY_did():
    """The verdict is only as good as the fact it is given. `done_ops` is the record of mutations that
    really ran — not what the model said it would do, which is precisely what was unreliable here."""
    done_ops.note("youtube", "search", {"query": "vídeos del Apolo"})
    q = redo_decision.question()
    assert q and "youtube:search" in q["instructions"]
    assert "vídeos del Apolo" in q["instructions"], "the detail he is correcting has to be in front of it"
    assert redo_decision.REDO_KEY in turn_brief.build("He dicho, Apollo once.")


def test_an_op_from_half_an_hour_ago_is_not_what_we_just_did():
    """A correction follows its target within a turn or two — both measured ones were inside 20 s.

    The first version of this test moved the op back by `WINDOW_S + 60`, which is true for ANY window and
    proved nothing: its disarm (widening the window to 99999 s) came back GREEN. It is the DISTANCE that
    is the decision, so the distance is what gets pinned. `done_ops.WINDOW_S` is 30 minutes because it
    answers a different question — whether a destructive op already ran — and inheriting it here would let
    a sentence half an hour later re-run an old op.
    """
    assert redo_decision.WINDOW_S < done_ops.WINDOW_S / 4, (
        "«what we just did» is a conversational distance, not a session-long one")
    done_ops.note("youtube", "search", {"query": "vídeos del Apolo"})
    done_ops._DONE[-1]["at"] -= 600            # ten minutes: well inside done_ops', far outside this one
    assert redo_decision.question() is None, "ten minutes later he is starting something new"
    done_ops._DONE[-1]["at"] += 600 - 20       # …and twenty seconds later he is still correcting
    assert redo_decision.question() is not None


# ── 2 · THE INCIDENT ──────────────────────────────────────────────────────────────────────────────────
def test_the_correction_that_was_swallowed_twice_now_lands():
    """«He dicho, Apollo once.» — no media verb, no media noun, `screen_action=none`. It is a correction
    of the search that just ran, and the model had already emitted the right call."""
    done_ops.note("youtube", "search", {"query": "vídeos del Apolo"})
    text = "He dicho, Apollo once."
    assert not canvas_license.video_license(text, "", brief=_brief({})), (
        "with no verdict at all this stays refused — the grammar was never the thing that changed")
    brief = _brief({redo_decision.REDO_KEY: ("corrects_last", 0.91)})
    assert canvas_license.video_license(text, "", brief=brief), (
        "THE BUG: the right call was emitted and a guard ate it, twice in a row, while the agent said "
        "out loud that it was acting on it")


def test_a_correction_of_ANOTHER_card_does_not_license_a_video_load():
    """A correction grants the licence of the op it corrects and only that one. Without this, complaining
    about the agenda would reload whatever is playing — the V2-677 failure with a new door."""
    done_ops.note("agenda", "delete_task", {"n": 4})
    brief = _brief({redo_decision.REDO_KEY: ("corrects_last", 0.95)})
    assert not canvas_license.video_license("no era esa, era la otra", "", brief=brief)


def test_an_unsure_correction_licenses_nothing():
    """The gate is the same one every verdict reader uses. A shrug keeps today's path."""
    done_ops.note("youtube", "search", {"query": "vídeos del Apolo"})
    brief = _brief({redo_decision.REDO_KEY: ("corrects_last", 0.31)})
    assert not canvas_license.video_license("He dicho, Apollo once.", "", brief=brief)


def test_a_NEW_request_is_not_a_correction():
    done_ops.note("youtube", "search", {"query": "vídeos del Apolo"})
    brief = _brief({redo_decision.REDO_KEY: ("new_request", 0.97)})
    assert not canvas_license.video_license("¿qué tiempo hace mañana?", "", brief=brief)


# ── 3 · AND A SEARCH DOES NOT START A CODING AGENT ────────────────────────────────────────────────────
def test_a_one_call_repair_is_handed_back_to_the_turn_instead_of_a_worker():
    """The escalation that ran a browser for four minutes, verbatim from the session."""
    from nucleo.susurro import apply
    req = ("Lanza en YouTube una búsqueda de la misión Apollo 11 (NASA, 1969) y refresca el widget de "
           "vídeos con esos resultados")
    assert apply._a_card_already_does_this(req) == "", (
        "with nothing just done, the premise «the fast brain was working on this and failed to fire» is "
        "not met — and this must lean towards escalating")
    done_ops.note("youtube", "search", {"query": "vídeos del Apolo"})
    assert apply._a_card_already_does_this(req) == "youtube"


def test_a_real_errand_still_gets_its_worker():
    """The gate that keeps this from eating the thing Brain Workers exist for. «Búscame un restaurante y
    apúntalo en la agenda» NAMES a card, which is why naming one cannot be the whole test."""
    from nucleo.susurro import apply
    done_ops.note("agenda", "add_task", {"title": "algo"})
    assert apply._a_card_already_does_this(
        "Búscame un restaurante para mañana por la noche en Madrid y resérvalo") == "", (
        "degrading a cold errand would take the worker away from exactly the work it exists for")
