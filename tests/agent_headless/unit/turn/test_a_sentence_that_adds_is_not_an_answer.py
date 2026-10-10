"""A sentence that adds or insists is not an answer to the parked errand's yes/no (three-tasks-at-once, 2026-10-10).

Measured in sandbox 20261010-145227-es. Two errands were parked on a question (the report on «Esto mueve dinero»,
the game on «¿La hago?»), and the operator went on talking about his three errands:

    «Vale. Del monitor que no se te vaya de presupuesto, ¿eh? 150 tope.»   -> confirm_task      (built the game)
    «Y el juego no te olvides, ¿eh? Que son tres, no dos.»                  -> confirm_task_no   (DROPPED the report)

Neither sentence answers either question. The task gate read the bare yes/no WORDS — «vale» in the first, the
«no» of «no te olvides» and «no dos» in the second — over the whole turn, and the whole turn included the
[SISTEMA] notes, whose own «sin tu OK» / «Si no te he entendido mal» took part in the vote. The widget gate
already had the right shape (V2 demo pass 45: a yes/no with more words is judged against the question it would
answer); the task gate never got it. The same reading now governs both: a plain yes/no answers; a longer
sentence answers only when the judge says it answers THIS question, or — with no judge — when the turn's verdict
reads it as an answer. Otherwise it stays waiting: an ambiguous word is not an authorisation.
"""
from __future__ import annotations

import threading

import pytest

from nucleo import dispatch_confirm as dc
from nucleo.turn import confirm_gates as gates
from widgets import confirm as wconfirm

NOTES = ("[SISTEMA] Aviso para el operador (zaelar): Esto mueve dinero («Elaborar un informe…») y no hago ningún "
         "cargo sin tu OK. ¿Sigo? Díselo con tus palabras DESPUÉS de contestar a lo que te ha pedido — todavía no "
         "lo sabe.\n[SISTEMA] Aviso para el operador (zaelar): Si no te he entendido mal, me pides que te CONSTRUYA "
         "una tarjeta nueva («Construir un widget de un juego…»). ¿La hago?")


def _brief(kind: str, p: float = 0.95):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "result": {"request_type": {"choice": kind, "confidence": p, "probs": {kind: p}}},
            "_call_id": "t", "turn_id": "t", "open_ids": []}


@pytest.fixture
def parked(monkeypatch):
    relaunched: list = []
    monkeypatch.setattr("nucleo.flash.escalate.escalate_to_slowbrain",
                        lambda req, context=None: relaunched.append(req) or 1)
    monkeypatch.setattr(dc, "_PENDING_CONFIRM", {})
    import time
    dc._PENDING_CONFIRM["7"] = {
        "request": "Construir un widget de un juego de plataformas tipo Super Mario", "kind": "code",
        "trusted": True, "context": {}, "question": "Si no te he entendido mal, me pides que te CONSTRUYA una "
        "tarjeta nueva. ¿La hago?", "sheet": "", "code_change": "create", "ts": time.time()}
    return relaunched


@pytest.mark.parametrize("said", [
    "Y el juego no te olvides, ¿eh? Que son tres, no dos.",
    "Vale. Del monitor que no se te vaya de presupuesto, ¿eh? 150 tope.",
    "Cool. And make that one jump higher, okay? Like really springy.",
])
def test_a_sentence_about_his_errands_leaves_the_question_waiting(parked, said):
    ans = gates.resolve_all(said, brief=_brief("order"))
    assert not ans, f"«{said}» was read as {'YES' if ans.yes else 'NO'} to the parked build"
    assert "7" in dc._PENDING_CONFIRM and not parked


def test_with_no_verdict_at_all_a_long_sentence_still_answers_nothing(parked):
    assert not gates.resolve_all("Y el juego no te olvides, ¿eh? Que son tres, no dos.")
    assert "7" in dc._PENDING_CONFIRM


def test_the_notes_glued_in_front_never_vote(parked):
    """«sin tu OK» belongs to OUR notice; the operator's own words here ask about something else."""
    assert not gates.resolve_all(NOTES + "\n\n¿Y el monitor qué?")
    assert "7" in dc._PENDING_CONFIRM


@pytest.mark.parametrize("said, yes", [("Sí", True), ("Sí, hazlo", True), ("No, déjalo", False),
                                       (NOTES + "\n\nsí", True), ("ok go ahead", True)])
def test_a_plain_yes_or_no_still_answers_at_once(parked, said, yes):
    ans = gates.resolve_all(said)
    assert ans and ans.gate == "task" and ans.yes is yes
    assert "7" not in dc._PENDING_CONFIRM
    assert bool(parked) is yes


def test_a_long_reply_the_verdict_reads_as_an_answer_answers(parked):
    ans = gates.resolve_all("Sí, venga, adelante con eso que te he dicho", brief=_brief("answer"))
    assert ans and ans.yes and parked


def test_the_judge_says_yes_to_a_long_reply_that_answers(parked, monkeypatch):
    asked: list = []
    monkeypatch.setattr(wconfirm, "_judge", lambda q, r, timeout=4.0: asked.append(q) or "yes")
    ans = gates.resolve_all("Vale, sí, móntalo, que tengo ganas de probarlo ya")
    assert ans and ans.yes and parked
    assert asked and "CONSTRUYA" in asked[0], "the judge must be shown the PARKED errand's own question"


def test_the_judge_overrules_a_verdict_that_read_an_answer(parked, monkeypatch):
    monkeypatch.setattr(wconfirm, "_judge", lambda q, r, timeout=4.0: "other")
    assert not gates.resolve_all("Vale, y del monitor que no pase de 150, ¿eh?", brief=_brief("answer"))
    assert "7" in dc._PENDING_CONFIRM and not parked
