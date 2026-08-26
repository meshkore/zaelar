"""V2-342 — on FRICTION with a live worker, the answer is to INJECT, and a kill no longer throws the work away.

Measured in session 7575e81a (search-buy-used-car, 2026-08-26 13:33-13:54): 3 workers over 21.6 min. The
person complains («lleva tantos minutos sin nada») at 13:34:37, the brain does NOTHING with the live worker,
and 35 s later the person orders the kill themself («sepárala y lánzala otra vez desde cero») — twice. The
first two workers were thrown away whole; only the third delivered. Two thirds of the time in discarded work,
and the loop feeds itself: slow → complaint → relaunch from zero → slower.

Three coordinated cuts, one defect:
  · the workers directive teaches the complaint fork: inject «deliver what you have NOW», killing is reserved
    for an explicit order or a stall the state shows;
  · a CANCELLED web errand keeps its resumable trace (`_leave_resume`) — stopping erases the PROCESS (tab
    closed, no auto-resume: «parar es parar», V2-092), not the road walked: the CLI native session keeps all
    its reasoning and an explicit relaunch inherits it;
  · `_find_resume` scores against the SMALLER word set (floor 3): the real relaunch order carries 47 content
    words of pacing instructions, and Jaccard scored the contained errand at 0.208 — under every sane
    threshold — while 11 of its 17 key words are right there in the order (0.647).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from nucleo import dispatch
from nucleo.workers import resume as _wres


# The REAL strings of the measured session (goal truncated at the record's cap, order verbatim).
GOAL = ("Busca coches de segunda mano en venta con estas condiciones: diésel, no muy viejo (a partir de "
        "2015 aproximadamente), y presupuesto máximo de 12.000 euros. Busca en Madrid (España).")[:200]
RELANZA = ("Relanza desde cero la búsqueda de coches de segunda mano en venta para Marc con estas "
           "condiciones: coche no muy viejo, motor diésel y presupuesto máximo de 12.000 €. Busca en "
           "marketplaces de segunda mano (Wallapop, Coches.net, etc.). Esta vez ve reportando avances por "
           "pasos y no te quedes atascada en silencio: si una fuente falla o tarda, avanza con las demás y "
           "notifica el progreso. El objetivo es ir sacando coches candidatos en pantalla para Marc, que "
           "necesita el coche pronto. Informa en cuanto tengas el primer coche con su nombre y precio.")


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    # V2-342: el subsistema vive en `nucleo/workers/resume.py`; se parchea AHÍ, que es donde las funciones
    # leen sus globals — parchear el alias de dispatch dejaría el dict real intacto y el test mediría aire.
    from nucleo.workers import resume as _wres
    monkeypatch.setattr(_wres, "_WEB_RESUME", {}, raising=False)
    monkeypatch.setattr(_wres, "_resume_persist", lambda: None, raising=False)
    yield


def _close(status: str, *, ok: bool = False, sid: str = "cli-7575e81a", nav: str = "") -> None:
    rec = SimpleNamespace(ok=ok, status=status, native_sid=sid)
    dispatch._leave_resume(rec, nav_tid=nav, resume=None, req=GOAL, key="1", brief=False, prev_count=0)


def test_a_cancelled_errand_leaves_its_resumable_trace():
    _close("cancelled")
    ent = dispatch._find_resume(RELANZA, take=True)
    assert ent and ent.get("native_sid") == "cli-7575e81a", _wres._WEB_RESUME
    # consumed: a second escalation of the same order must not resume the same CLI session (V2-237)
    assert dispatch._find_resume(RELANZA) is None


def test_a_completed_errand_leaves_nothing():
    _wres._WEB_RESUME[dispatch._goal_key(GOAL)] = {"ts": 0}
    _close("done", ok=True)
    assert _wres._WEB_RESUME == {}


def test_a_cancelled_errand_with_no_session_and_no_tab_leaves_nothing():
    _close("cancelled", sid="")
    assert _wres._WEB_RESUME == {}


def test_the_measured_relaunch_order_matches_and_an_unrelated_errand_does_not():
    _close("cancelled")
    assert dispatch._find_resume(RELANZA) is not None
    assert dispatch._find_resume("busca un monitor de 27 pulgadas por menos de 150 euros") is None
    # a one-word order cannot walk away with whatever errand is pending (the floor of 3)
    assert dispatch._find_resume("busca") is None


def test_the_directive_teaches_inject_on_complaint_before_the_kill(monkeypatch):
    from nucleo.flash import prompt as P
    monkeypatch.setattr(dispatch, "has_active", lambda: True)
    text = P._workers_directive()
    assert "Si se QUEJA" in text and "ENTREGUE YA" in text, text
    # the complaint fork must come BEFORE the kill sentence: the first imperative wins (V2-318)
    assert text.index("Si se QUEJA") < text.index("Si pide PARARLO"), text
    # …and killing stays available for the explicit order: teaching inject must not unteach stop
    assert "stop_worker" in text
