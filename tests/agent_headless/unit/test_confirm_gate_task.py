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

    Corregido el 2026-08-20 (V2-190): este test EXIGÍA que la línea de estado se quedara vacía al caducar, y
    eso resultó ser el daño. Medido en `renew-gym-membership__es`: al vaciarse, el turno dejó de tener
    cualquier hecho sobre aquella tarea y volvió a su propia frase anterior («empiezo ya con la renovación»),
    contestando «sigo sin novedades de la web de Basic-Fit» sobre algo que nunca abrió una página.

    Lo que este test protegía —que el GATE caduque, para que un «sí» de media hora después no arme un cobro—
    sigue exigido en la primera aserción y en `test_but_the_gate_itself_still_expires`. Lo que cambia es que
    caducar deja de BORRAR el hecho."""
    dispatch._EXPIRED_CONFIRM.clear()
    dispatch.remember_confirm("9", "paga la factura de la luz", _Task())
    dispatch._PENDING_CONFIRM["9"]["ts"] = time.time() - dispatch._CONFIRM_TTL - 1
    assert dispatch.pending_confirm() is None          # el gate caduca: nada que un «sí» tardío pueda armar
    assert "PENDIENTE" not in dispatch.confirm_line()  # ya no se anuncia como si siguiera esperando…
    assert "CADUCÓ" in dispatch.confirm_line()         # …pero el hecho de que hubo una pregunta sobrevive
    dispatch._EXPIRED_CONFIRM.clear()


def test_a_second_irreversible_ask_supersedes_the_first():
    dispatch.remember_confirm("9", "paga la factura de la luz", _Task())
    time.sleep(0.01)
    dispatch.remember_confirm("10", "cancela mi suscripción a Netflix", _Task())
    assert dispatch.pending_confirm()["task_id"] == "10"


# ── DINERO vs simplemente irreversible (V2-129, 2026-08-18) ──────────────────────────────────────────────
# El caso `renew-gym-membership__es` acabó con el propio tester frenando la ejecución: «no me has dicho cuánto
# vas a pagar ni me has pedido confirmación. No hagas el cargo hasta que me pases el importe y te confirme».
# Tenía razón dos veces: no había importe, y no podía haberlo (nadie había mirado la cuota). Una pregunta
# genérica no dice lo único que hay que oír antes de autorizar un cargo — que nada se paga sin ver la cifra.
def test_a_money_order_promises_the_amount_before_charging():
    q = danger.confirm_question("Renueva mi cuota del gimnasio de este mes")
    assert "mueve dinero" in q.lower()
    assert "importe" in q                     # la promesa que el tester echó en falta
    assert "sin tu OK" in q


def test_a_non_money_irreversible_keeps_the_generic_question():
    """Borrar una cuenta o publicar un anuncio es irreversible pero no cuesta nada: prometerle un importe sería
    una frase sin sentido."""
    for req in ("borra la cuenta", "publica el anuncio en Wallapop", "cancela mi suscripción a Netflix"):
        q = danger.confirm_question(req)
        assert "mueve dinero" not in q.lower(), req
        assert "irreversible" in q, req


def test_moves_money_is_a_SUBSET_of_dangerous():
    """Todo lo que mueve dinero para en el gate; no todo lo que para en el gate mueve dinero."""
    for req in ("Paga la factura de la luz antes del día 5", "renuévame la cuota del gimnasio",
                "compra la moto que te he dicho", "contrata la tarifa nueva de la luz"):
        assert danger.moves_money(req) and danger.is_dangerous(req), req
    for req in ("borra la cuenta", "publica el anuncio en Wallapop"):
        assert danger.is_dangerous(req) and not danger.moves_money(req), req


def test_a_reminder_about_money_moves_no_money():
    """Mismo recorte de recado que el resto del módulo: «recuérdame pagar la cuota» no cobra nada."""
    assert not danger.moves_money("recuérdame pagar la cuota del gimnasio")


def test_the_live_line_carries_the_amount_promise(monkeypatch):
    """El turno siguiente no puede contradecir lo que se le acaba de prometer al operador."""
    dispatch.remember_confirm("9", "Renueva mi cuota del gimnasio de este mes", _Task())
    line = dispatch.confirm_line()
    assert "MUEVE DINERO" in line
    assert "importe exacto ANTES de cobrar" in line
    dispatch._PENDING_CONFIRM.clear()
    dispatch.remember_confirm("10", "borra la cuenta", _Task())
    assert "MUEVE DINERO" not in dispatch.confirm_line()


# ── V2-190: una confirmación que CADUCA sin respuesta también es un hecho ─────────────────────────────────
#
# `renew-gym-membership__es`, 2026-08-20 01:01 (overall 2/5, mecanismo 1). El gate aparcó la renovación, se le
# preguntó al operador, pasaron cinco minutos dentro de una conversación normal, `_sweep_confirm` tiró la
# entrada, `confirm_line()` se quedó vacía — y a partir de ese turno el estado no decía NADA de aquello. El
# modelo volvió a lo único que le quedaba, su propio «Empiezo ya con la renovación en Basic-Fit», y contestó
# «sigo sin novedades de la web de Basic-Fit» sobre una tarea cuyo registro decía `status=done url= shot_rev=0`:
# no había abierto una sola página, y nunca la iba a abrir.
#
# El TTL NO es el fallo y no se toca: un «¿de verdad lo pago?» contestado que sí cuarenta minutos después es
# justo lo que protege. Lo que estaba mal es que caducar el GATE borraba también la MEMORIA de que hubo uno.
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
    assert "gimnasio" in line                      # y CUÁL, o no se puede retomar


def test_but_the_gate_itself_still_expires():
    """La mitad de seguridad, intacta: un «sí» tardío no puede armar una acción irreversible que se preguntó
    hace media hora. Sin este test, «recuerda el caducado» y «no caduca nunca» pasan igual."""
    tid = _ask()
    dispatch._PENDING_CONFIRM[tid]["ts"] = time.time() - (dispatch._CONFIRM_TTL + 100)
    assert dispatch.pending_confirm() is None
    assert dispatch.resolve_confirm(True) is None


def test_a_live_question_wins_over_the_memory_of_an_expired_one():
    """Lo que está esperando AHORA es más importante que lo que caducó: al revés, el turno hablaría del pasado
    teniendo una pregunta viva delante."""
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
    """Un caducado de hace una hora ya no es del turno; seguir sacándolo sería ruido en cada estado."""
    tid = _ask()
    dispatch._PENDING_CONFIRM[tid]["ts"] = time.time() - (dispatch._CONFIRM_TTL + 100)
    dispatch.confirm_line()
    dispatch._EXPIRED_CONFIRM[tid]["expired_at"] = time.time() - (dispatch._EXPIRED_MEMORY_S + 100)
    assert dispatch.confirm_line() == ""


def test_and_it_reaches_the_live_state():
    """El fallo de esta casa que se repite: el hecho existe y no llega al sitio donde se decide."""
    from nucleo.flash import prompt as _p

    tid = _ask()
    dispatch._PENDING_CONFIRM[tid]["ts"] = time.time() - (dispatch._CONFIRM_TTL + 100)
    assert "CADUCÓ" in _p.live_state()
    dispatch._EXPIRED_CONFIRM.clear()
