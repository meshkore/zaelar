"""The confirm-gate for an irreversible TASK is a question with an answer (V2-126, 2026-08-18).

It used to be a dead end. `dispatch.run_task` stopped the task, spoke the question through the proactive rail,
dropped the SessionRecord — and NOTHING anywhere ever set `context["confirmed"]`, so a «sí» from the operator
had nowhere to go. Worse, the task vanished from `pending_summaries()`, so the next turn saw zero live work and
went back to narrating progress that did not exist (`cancel-subscription-before-charge__es`, and
`pay-known-bill__es` where three tasks were gated and none of it was ever told to the operator).
"""
from __future__ import annotations

import time

import pytest

from nucleo import danger, dispatch


class _Task:
    def __init__(self, kind="web", trusted=True, context=None):
        self.kind, self.trusted, self.context = kind, trusted, dict(context or {})


@pytest.fixture(autouse=True)
def clean():
    dispatch._PENDING_CONFIRM.clear()
    yield
    dispatch._PENDING_CONFIRM.clear()


def test_the_question_survives_the_turn_that_asked_it():
    dispatch.remember_confirm("9", "cancela mi suscripción a Netflix", _Task())
    p = dispatch.pending_confirm()
    assert p and p["task_id"] == "9"
    assert p["question"] == danger.confirm_question("cancela mi suscripción a Netflix")


def test_the_brain_can_SEE_that_something_is_parked():
    """The half that turned a gated task into narrated progress: with the record gone and no line in the live
    state, the next turn had no way to know anything was waiting."""
    assert dispatch.confirm_line() == ""
    dispatch.remember_confirm("9", "paga la factura de la luz", _Task())
    line = dispatch.confirm_line()
    assert "CONFIRMACIÓN PENDIENTE" in line
    assert "no ha empezado nada" in line          # explicitly contradicts "ya está en marcha"
    assert "paga la factura de la luz" in line


def test_the_live_state_carries_it():
    from nucleo.flash import prompt
    dispatch.remember_confirm("9", "paga la factura de la luz", _Task())
    assert "CONFIRMACIÓN PENDIENTE de una acción IRREVERSIBLE" in prompt.live_state()


def test_a_yes_re_dispatches_the_SAME_request_with_confirmed_set(monkeypatch):
    sent: list = []
    from nucleo.flash import escalate as esc
    monkeypatch.setattr(esc, "escalate_to_slowbrain",
                        lambda req, context=None: sent.append((req, dict(context or {}))) or 1)
    dispatch.remember_confirm("9", "cancela mi suscripción a Netflix", _Task(context={"src": "probe"}))
    out = dispatch.resolve_confirm(True)
    assert out["ok"] is True
    assert len(sent) == 1
    req, ctx = sent[0]
    assert req == "cancela mi suscripción a Netflix"
    assert ctx["confirmed"] is True        # …which is what makes the gate let it through this time
    assert ctx["src"] == "probe"           # the original context is preserved, not rebuilt
    assert dispatch.pending_confirm() is None


def test_a_no_drops_it_and_launches_nothing(monkeypatch):
    sent: list = []
    from nucleo.flash import escalate as esc
    monkeypatch.setattr(esc, "escalate_to_slowbrain", lambda req, context=None: sent.append(req) or 1)
    dispatch.remember_confirm("9", "paga la factura de la luz", _Task())
    out = dispatch.resolve_confirm(False)
    assert out["ok"] is False
    assert sent == []
    assert dispatch.pending_confirm() is None


def test_answering_when_nothing_is_pending_is_a_no_op():
    assert dispatch.resolve_confirm(True) is None


def test_a_confirmation_nobody_answers_expires():
    """Same reason the widget gate has a TTL: a question that hangs forever silently blocks the next one.

    Corrected on 2026-08-20 (V2-190): this test REQUIRED the status line to become empty on expiry, and
    that turned out to be the harm. Observed in `renew-gym-membership__es`: once it became empty, the turn
    no longer had any fact about that task and returned to its own earlier phrase («empiezo ya con la renovación»),
    replying «sigo sin novedades de la web de Basic-Fit» about something that had never opened a page.

    What this test protected —the GATE expiring, so that a «sí» half an hour later cannot initiate a charge—
    is still required by the first assertion and by `test_but_the_gate_itself_still_expires`. What changes is
    that expiry no longer DELETES the fact."""
    dispatch._EXPIRED_CONFIRM.clear()
    dispatch.remember_confirm("9", "paga la factura de la luz", _Task())
    dispatch._PENDING_CONFIRM["9"]["ts"] = time.time() - dispatch._CONFIRM_TTL - 1
    assert dispatch.pending_confirm() is None          # the gate expires: nothing for a late «sí» to initiate
    assert "PENDIENTE" not in dispatch.confirm_line()  # it is no longer announced as if it were still waiting…
    assert "CADUCÓ" in dispatch.confirm_line()         # …but the fact that there was a question survives
    dispatch._EXPIRED_CONFIRM.clear()


def test_a_second_irreversible_ask_supersedes_the_first():
    dispatch.remember_confirm("9", "paga la factura de la luz", _Task())
    time.sleep(0.01)
    dispatch.remember_confirm("10", "cancela mi suscripción a Netflix", _Task())
    assert dispatch.pending_confirm()["task_id"] == "10"


# ── DINERO vs simplemente irreversible (V2-129, 2026-08-18) ──────────────────────────────────────────────
# The `renew-gym-membership__es` case ended with the tester itself stopping execution: «no me has dicho cuánto
# vas a pagar ni me has pedido confirmación. No hagas el cargo hasta que me pases el importe y te confirme».
# It was right twice: there was no amount, and there could not have been one (nobody had checked the fee). A
# generic question does not say the one thing that must be heard before authorizing a charge — that nothing is
# paid without seeing the amount.
def test_a_money_order_promises_the_amount_before_charging():
    q = danger.confirm_question("Renueva mi cuota del gimnasio de este mes")
    assert "mueve dinero" in q.lower()
    assert "importe" in q                     # la promesa que el tester echó en falta
    assert "sin tu OK" in q


def test_a_non_money_irreversible_keeps_the_generic_question():
    """Deleting an account or publishing an ad is irreversible but costs nothing: promising an amount would be
    meaningless."""
    for req in ("borra la cuenta", "publica el anuncio en Wallapop", "cancela mi suscripción a Netflix"):
        q = danger.confirm_question(req)
        assert "mueve dinero" not in q.lower(), req
        assert "irreversible" in q, req


def test_moves_money_is_a_SUBSET_of_dangerous():
    """Everything that moves money stops at the gate; not everything that stops at the gate moves money."""
    for req in ("Paga la factura de la luz antes del día 5", "renuévame la cuota del gimnasio",
                "compra la moto que te he dicho", "contrata la tarifa nueva de la luz"):
        assert danger.moves_money(req) and danger.is_dangerous(req), req
    for req in ("borra la cuenta", "publica el anuncio en Wallapop"):
        assert danger.is_dangerous(req) and not danger.moves_money(req), req


def test_a_reminder_about_money_moves_no_money():
    """The same reminder distinction as in the rest of the module: «recuérdame pagar la cuota» does not charge anything."""
    assert not danger.moves_money("recuérdame pagar la cuota del gimnasio")


def test_the_live_line_carries_the_amount_promise(monkeypatch):
    """The next turn must not contradict what was just promised to the operator."""
    dispatch.remember_confirm("9", "Renueva mi cuota del gimnasio de este mes", _Task())
    line = dispatch.confirm_line()
    assert "MUEVE DINERO" in line
    assert "importe exacto ANTES de cobrar" in line
    dispatch._PENDING_CONFIRM.clear()
    dispatch.remember_confirm("10", "borra la cuenta", _Task())
    assert "MUEVE DINERO" not in dispatch.confirm_line()


# ── V2-190: a confirmation that EXPIRES without a response is also a fact ─────────────────────────────────
#
# `renew-gym-membership__es`, 2026-08-20 01:01 (overall 2/5, mechanism 1). The gate parked the renewal, the
# operator was asked, five minutes passed during a normal conversation, `_sweep_confirm` removed the
# entry, `confirm_line()` became empty — and from that turn onward the state said NOTHING about it. The
# model returned to the only thing it had left, its own «Empiezo ya con la renovación en Basic-Fit», and replied
# «sigo sin novedades de la web de Basic-Fit» about a task whose record said `status=done url= shot_rev=0`:
# it had not opened a single page, and never would.
#
# The TTL is NOT the problem and is not changed: a «¿de verdad lo pago?» answered yes forty minutes later is
# exactly what it protects against. What was wrong is that expiring the GATE also erased the MEMORY that one existed.
def _ask(request="Renueva mi cuota del gimnasio de este mes.", tid="gym1"):
    dispatch._PENDING_CONFIRM.clear()
    dispatch._EXPIRED_CONFIRM.clear()
    dispatch.remember_confirm(tid, request, _Task())
    return tid


def test_an_expired_confirmation_still_says_the_task_never_started():
    tid = _ask()
    dispatch._PENDING_CONFIRM[tid]["ts"] = time.time() - (dispatch._CONFIRM_TTL + 100)
    line = dispatch.confirm_line()
    assert "CADUCÓ" in line and "NUNCA EMPEZÓ" in line
    assert "gimnasio" in line                      # and WHICH one, or it cannot be resumed


def test_but_the_gate_itself_still_expires():
    """The safety half remains intact: a late «sí» cannot initiate an irreversible action that was asked about
    half an hour ago. Without this test, «remember the expired one» and «never expires» would both pass."""
    tid = _ask()
    dispatch._PENDING_CONFIRM[tid]["ts"] = time.time() - (dispatch._CONFIRM_TTL + 100)
    assert dispatch.pending_confirm() is None
    assert dispatch.resolve_confirm(True) is None


def test_a_live_question_wins_over_the_memory_of_an_expired_one():
    """What is waiting NOW is more important than what expired: otherwise, the turn would talk about the past
    while having a live question in front of it."""
    old = _ask(tid="gym1")
    dispatch._PENDING_CONFIRM[old]["ts"] = time.time() - (dispatch._CONFIRM_TTL + 100)
    dispatch.confirm_line()                                    # fuerza el barrido
    dispatch.remember_confirm("bill1", "Paga la factura de la luz", _Task())
    line = dispatch.confirm_line()
    assert "PENDIENTE" in line and "factura" in line
    assert "CADUCÓ" not in line


def test_and_re_asking_the_same_thing_clears_its_expired_record():
    tid = _ask()
    dispatch._PENDING_CONFIRM[tid]["ts"] = time.time() - (dispatch._CONFIRM_TTL + 100)
    dispatch.confirm_line()
    assert dispatch._EXPIRED_CONFIRM
    dispatch.remember_confirm(tid, "Renueva mi cuota del gimnasio de este mes.", _Task())
    assert tid not in dispatch._EXPIRED_CONFIRM
    assert "PENDIENTE" in dispatch.confirm_line()


def test_the_memory_of_an_expired_one_does_not_last_forever():
    """An expired item from an hour ago is no longer part of the turn; continuing to surface it would add noise to every state."""
    tid = _ask()
    dispatch._PENDING_CONFIRM[tid]["ts"] = time.time() - (dispatch._CONFIRM_TTL + 100)
    dispatch.confirm_line()
    dispatch._EXPIRED_CONFIRM[tid]["expired_at"] = time.time() - (dispatch._EXPIRED_MEMORY_S + 100)
    assert dispatch.confirm_line() == ""


def test_and_it_reaches_the_live_state():
    """This codebase's recurring failure: the fact exists but does not reach the place where the decision is made."""
    from nucleo.flash import prompt as _p

    tid = _ask()
    dispatch._PENDING_CONFIRM[tid]["ts"] = time.time() - (dispatch._CONFIRM_TTL + 100)
    assert "CADUCÓ" in _p.live_state()
    dispatch._EXPIRED_CONFIRM.clear()
