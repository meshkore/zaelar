"""V2-221 — the fact was in the prompt and the instruction only applied «if he asks».

Measured by the harness on `hotel-under-15-days` (19:12), reading the system prompt of every turn:

  turno 2: «TAREAS DE FONDO — YA ACABADAS: «Reservar una noche de hotel…» FALLÓ»
  turnos 3,4,5,6,7,8: lo mismo, la tarea muerta en el prompt cada vez
  respuesta, ocho veces: «sigo con ello, te aviso»

No wall, no question — a dead task, stated on its own line of the prompt, ignored eight times in a row. That
separates the two halves of this whole area without ambiguity: DELIVERY was fixed (V2-198 puts the fact in the
prompt; V2-220 makes proactive notices arrive on the text channel), and what remains is OBEDIENCE.

The cause is the same cut V2-185 made for the wall: V2-198's instruction was CONDITIONAL — «si el operador
pregunta por ello» — and a dead task is not a pending question. It is a person waiting for something that will
never arrive. While the reassuring half is the one that says what to DO, the model believes that one.
"""
import pytest

from nucleo.flash import prompt as P


def _state(monkeypatch, ended):
    import nucleo.dispatch as D
    monkeypatch.setattr(D, "recently_ended_sessions", lambda: ended, raising=False)
    return P.live_state()


_FAILED = [{"goal": "Reservar una noche de hotel de 4 estrellas en Sevilla", "status": "error", "ok": False}]
_OK = [{"goal": "Buscar un monitor barato", "status": "done", "ok": True, "summary": "3 candidatos"}]


def test_a_failed_task_is_told_WITHOUT_being_asked(monkeypatch):
    st = _state(monkeypatch, _FAILED)
    assert "NO ACABÓ BIEN" in st
    assert "DÍSELO EN ESTE TURNO" in st
    assert "aunque no pregunte" in st


def test_it_names_WHICH_task(monkeypatch):
    """V2-193: with several alive, «esa tarea» points at any of them. An imperative that does not name its own
    subject is how the theatre task got delivered while the operator asked about his gym."""
    st = _state(monkeypatch, _FAILED)
    assert "Sevilla" in st


def test_it_forbids_the_exact_phrase_that_was_measured(monkeypatch):
    """«sigo con ello, te aviso» is what it answered eight times. Naming the phrase is what turns a prohibition
    into something the model can check itself against — V2-185 and V2-215 both needed this."""
    st = _state(monkeypatch, _FAILED)
    assert "sigo con ello" in st and "te aviso" in st


def test_it_offers_a_way_out(monkeypatch):
    """«Falló» alone is a diagnosis. What the operator can act on is what now."""
    st = _state(monkeypatch, _FAILED)
    for out in ("reintentarlo", "otra vía", "dejarlo"):
        assert out in st, out


def test_it_does_not_ask_to_repeat_itself_every_turn(monkeypatch):
    """The record has a 5-minute TTL, so this line rides several turns. Without this clause the fix for silence
    becomes the fix for a broken record — which is the defect V2-189 measured («vale, dame un momento» four
    times, word for word)."""
    st = _state(monkeypatch, _FAILED)
    assert "no lo repitas" in st


def test_a_task_that_ended_WELL_keeps_the_old_conditional_wording(monkeypatch):
    """Sensitivity, and the reason this is a split and not a rewrite: a task that finished fine is genuinely an
    «if he asks». Shouting about it would push the turn to report bookkeeping nobody wanted."""
    st = _state(monkeypatch, _OK)
    assert "TERMINÓ" in st
    assert "NO ACABÓ BIEN" not in st
    assert "si el operador pregunta por ello" in st


def test_a_CANCELLED_task_is_not_treated_as_a_failure(monkeypatch):
    """V2-196: stopping is not failing. «No va a llegar» over something the operator himself killed invites him
    to fix a problem he already resolved."""
    st = _state(monkeypatch, [{"goal": "Buscar vuelos", "status": "cancelled", "ok": False}])
    assert "se PARÓ (cancelada)" in st
    assert "NO ACABÓ BIEN" not in st


def test_one_failure_among_several_still_fires(monkeypatch):
    """A good outcome next to a dead one must not bury the dead one."""
    st = _state(monkeypatch, _OK + _FAILED)
    assert "NO ACABÓ BIEN" in st and "Sevilla" in st


def test_nothing_ended_says_nothing(monkeypatch):
    st = _state(monkeypatch, [])
    assert "YA ACABADAS" not in st
