"""V2-202 — the confirm-gate stopped an irreversible click and asked NOBODY.

Measured on `find-theatre-tickets__es` (2026-08-20 13:33). Two halves of one hole, and each is invisible from
the other side:

    worker/navegador   Exit code 1 ERROR: acción «Comprar entradas» NO confirmada por el operador
    judge (dialogue)   «esperando una confirmación que nunca se pidió al usuario»

The gate did everything its own module asked of it — `tasks.ask()` wrote the question, set `needs_input`, and
`proactive.notify` fired. What it never had was a way OUT of the browser module and back:

  · `active_progress()` is the ONLY route a live task has into the prompt, and it dropped `question`, so the
    brain could not know there was anything to ask;
  · `waiting_id()` — the lookup built for exactly this — had ZERO callers in production, so even a spoken «sí»
    had nowhere to land. The card's button (`answer_task`) was the only door, and there is no card in front of
    someone who is talking.

So the operator was standing there willing to answer, was never asked, and the task died on its deadline while
the turn kept reporting progress. These tests walk both halves through the real functions.
"""
import importlib

import pytest


@pytest.fixture()
def tasks():
    t = importlib.import_module("widgets.navegador.tasks")
    t._tasks.clear()
    from widgets import confirm
    confirm.reset()
    return t


def test_the_question_reaches_the_state_the_brain_reads(tasks):
    """`ask()` writes the question; `active_progress()` must carry it. It did not, and that alone made the
    operator unaskable — everything downstream reads this dict, not the task store."""
    tid = tasks.create("comprar entradas del teatro")
    tasks.ask(tid, "Voy a pulsar «Comprar entradas». ¿Lo confirmo? (dime sí o no)")

    row = next(r for r in tasks.active_progress() if r["id"] == tid)
    assert "Comprar entradas" in row["question"]


def test_a_parked_task_stays_in_the_live_list(tasks):
    """`needs_input` is a LIVE state: a task waiting on the operator has not ended and must keep its line in the
    prompt. If it dropped off, the fix above would be delivering the question to nobody."""
    tid = tasks.create("comprar entradas del teatro")
    tasks.ask(tid, "¿Lo confirmo?")
    assert [r["id"] for r in tasks.active_progress()] == [tid]


def test_the_turn_says_it_is_asking_and_quotes_the_question():
    """The whole point: the state must ORDER the brain to ask, with the question in it. A line that merely says
    «parada» reproduces the measured failure — the model already had «parada» and narrated progress anyway."""
    t = importlib.import_module("widgets.navegador.tasks")
    t._tasks.clear()
    tid = t.create("comprar entradas del teatro")
    t.ask(tid, "Voy a pulsar «Comprar entradas». ¿Lo confirmo?")

    from nucleo.flash import prompt
    live = prompt.live_state()

    assert "ESTÁ PARADA ESPERANDO TU OK" in live
    assert "Comprar entradas" in live
    assert "PREGÚNTASELO EN ESTE TURNO" in live
    t._tasks.clear()


def test_the_spoken_yes_reaches_the_waiting_click(tasks):
    """The route back. `take_answer` is what the gate polls, so this is the exact byte the blocked coroutine
    consumes — not a proxy for it."""
    tid = tasks.create("comprar entradas del teatro")
    tasks.ask(tid, "¿Lo confirmo?")

    got = tasks.answer_from_turn("sí, dale")
    assert got == {"task_id": tid, "ok": True}
    assert tasks.take_answer(tid) == "sí, dale"
    assert tasks.get(tid)["status"] == "working"          # ya no espera: el gate puede seguir


def test_a_no_is_also_an_answer(tasks):
    """«no» must resolve the gate too. Left unanswered it would expire and be reported as a timeout, which is a
    different fact from a refusal — and the operator DID reply."""
    tid = tasks.create("comprar entradas del teatro")
    tasks.ask(tid, "¿Lo confirmo?")

    got = tasks.answer_from_turn("no, déjalo")
    assert got == {"task_id": tid, "ok": False}
    assert tasks.take_answer(tid) == "no, déjalo"


def test_conversation_is_not_an_answer(tasks):
    """A turn that is not a yes/no must NOT consume the question: swallowing «¿cuánto cuestan?» as an answer
    would be the mirror bug — clicking Buy because the operator asked about the price."""
    tid = tasks.create("comprar entradas del teatro")
    tasks.ask(tid, "¿Lo confirmo?")

    assert tasks.answer_from_turn("¿y cuánto cuestan?") is None
    assert tasks.take_answer(tid) == ""
    assert tasks.get(tid)["status"] == "needs_input"       # sigue esperando, que es la verdad


def test_nothing_waiting_means_nothing_answered(tasks):
    """A «sí» with no gate open must return None, not invent a resolution. This is what keeps the route from
    eating an affirmative that belonged to the conversation."""
    tasks.create("comprar entradas del teatro")
    assert tasks.answer_from_turn("sí") is None


def test_the_deadline_outlives_a_conversational_round_trip():
    """60 s was the card-button deadline. Through the conversation the answer cannot arrive that fast: the brain
    learns of the question when it composes its NEXT turn, asks then, and the operator answers on the turn after.
    Aligned with the sibling gate (`dispatch._CONFIRM_TTL`) — this is the number that made the measured run
    refuse a click with the operator standing right there."""
    from nucleo import dispatch
    from widgets.navegador import owner
    assert owner._CONFIRM_TIMEOUT >= dispatch._CONFIRM_TTL
