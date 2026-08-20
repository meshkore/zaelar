"""V2-224 — «¿ya se lo dije?» era una deducción del modelo, y tenía que ser un hecho nuestro.

V2-221 puso la instrucción incondicional («DÍSELO EN ESTE TURNO») y funcionó: el arnés midió 2 de 2 turnos
diciéndolo, en el turno 2, sin que nadie preguntara. Pero llevaba la anti-repetición DENTRO de la misma frase
—«si ya se lo dijiste en un turno anterior, no lo repitas»— y eso se midió en DOS rondas del MISMO commit con
resultados opuestos:

    ronda 5 → lo dijo en el turno 2 y lo REPITIÓ en el 5, 6, 7, 8 y 9.            (el disco rayado de V2-189)
    ronda 6 → lo dijo en el turno 2 y luego lo NEGÓ siete turnos: «Sigo con ello»,
              «Dame un momento», «Ahora te lo relanzo».

Mismo commit, misma cláusula, fallos contrarios. Eso no es un umbral mal puesto: es que el registro de «ya se lo
dije» no gobernaba la decisión. En una ronda no lo encontraba y repetía; en la otra lo encontraba y se callaba
ENTERO — y callar la repetición no es callar el estado.

Nosotros sabemos cuántos turnos han llevado ese final delante. Así que se cuenta, y cada turno recibe UNA
instrucción: la primera vez, dilo; a partir de ahí, no lo repitas PERO sigue muerta, y las frases
tranquilizadoras siguen prohibidas.
"""
import pytest

from nucleo import dispatch as d


class _Rec:
    def __init__(self, tid, goal, status="error", ok=False, summary=""):
        self.task_id, self.goal, self.status, self.ok, self.result_summary = tid, goal, status, ok, summary


@pytest.fixture(autouse=True)
def _clean():
    e = dict(d._ENDED_SESSIONS)
    d._ENDED_SESSIONS.clear()
    yield
    d._ENDED_SESSIONS.clear(); d._ENDED_SESSIONS.update(e)


GOAL = "Busca hoteles de 4 estrellas en Sevilla"


def _state(monkeypatch, rows):
    from nucleo.flash import prompt as P
    monkeypatch.setattr(d, "recently_ended_sessions", lambda: rows, raising=False)
    return P.live_state()


FAILED = [{"id": "1", "goal": GOAL, "status": "error", "ok": False, "summary": "", "ago_s": 5, "told": 0}]


def test_a_fresh_death_starts_at_zero():
    d._remember_ended(_Rec("1", GOAL))
    assert d.recently_ended_sessions()[0]["told"] == 0


def test_the_turn_that_carried_it_marks_it(monkeypatch):
    """El contador lo mueve el turno que lo llevó delante, no el que murió: entre la muerte y el prompt siguiente
    puede no haber ninguno."""
    d._remember_ended(_Rec("1", GOAL))
    _state(monkeypatch, d.recently_ended_sessions())
    assert d._ENDED_SESSIONS["1"]["told"] == 1


def test_the_FIRST_turn_gets_the_notice(monkeypatch):
    st = _state(monkeypatch, FAILED)
    assert "DÍSELO EN ESTE TURNO" in st


def test_and_the_ONES_AFTER_are_told_not_to_repeat_it(monkeypatch):
    st = _state(monkeypatch, [{**FAILED[0], "told": 1}])
    assert "NO se lo vuelvas a anunciar" in st
    assert "DÍSELO EN ESTE TURNO" not in st


def test_but_the_STATE_survives_the_silence(monkeypatch):
    """La mitad que la ronda 6 perdió: dejar de dar la noticia no es volver a «sigo con ello». La tarea sigue
    muerta y la frase tranquilizadora sigue prohibida."""
    st = _state(monkeypatch, [{**FAILED[0], "told": 3}])
    assert "SIGUE MUERTA" in st
    for banned in ("sigo con ello", "te aviso en cuanto lo tenga", "dame un momento"):
        assert banned in st.lower(), banned


def test_only_ONE_instruction_per_turn(monkeypatch):
    """La causa raíz: dos órdenes en la misma frase se resolvían a cara o cruz según la ronda."""
    first = _state(monkeypatch, FAILED)
    later = _state(monkeypatch, [{**FAILED[0], "told": 1}])
    assert ("DÍSELO EN ESTE TURNO" in first) != ("DÍSELO EN ESTE TURNO" in later)
    assert ("NO se lo vuelvas a anunciar" in first) != ("NO se lo vuelvas a anunciar" in later)


def test_a_task_that_ended_WELL_is_never_counted(monkeypatch):
    """Sensitivity: el contador es de MUERTES. Marcar un final bueno gastaría el primer turno de la siguiente."""
    ok = [{"id": "9", "goal": GOAL, "status": "done", "ok": True, "summary": "hecho", "ago_s": 2, "told": 0}]
    d._ENDED_SESSIONS["9"] = dict(ok[0])
    _state(monkeypatch, ok)
    assert d._ENDED_SESSIONS["9"]["told"] == 0


def test_a_CANCELLED_task_is_never_counted_either(monkeypatch):
    """V2-196: pararse no es fallar, y el operador ya lo sabe porque la paró él."""
    c = [{"id": "9", "goal": GOAL, "status": "cancelled", "ok": False, "summary": "", "ago_s": 2, "told": 0}]
    d._ENDED_SESSIONS["9"] = dict(c[0])
    _state(monkeypatch, c)
    assert d._ENDED_SESSIONS["9"]["told"] == 0


def test_marking_an_id_that_no_longer_exists_is_harmless():
    """El registro caduca a los 5 minutos; el turno que lo llevaba puede llegar tarde."""
    d.mark_death_reported(["no-existe", ""])
