"""V2-468 · un span de UN evento no dura cero, y leerlo así contradice el hecho que sí lo mide.

`audit.spans` viaja íntegro en el JSON que recibe el juez, con `first_ms` y `last_ms`. Para un span de UN
solo evento los dos coinciden, y de ahí se lee «duración 0 ms». Un rail que anuncia el arranque una vez y
se calla mientras trabaja tiene EXACTAMENTE esa forma — que es la del reproductor de música.

MEDIDO en `play-music-and-build-playlist` (2026-08-28 21:38, plató ES). El informe traía
`rail:music.playing` con `n: 1, first_ms: 7859, last_ms: 7859`, y `widgets_producing: ["musica"]` — el hecho
que de verdad contesta «¿sonaba algo?», enunciado en palabras dos líneas más arriba con «diga lo que diga el
resto». El juez escribió: «el span 'rail:music.playing' muestra una duración de 0ms (instantáneo) … se
considera que solo se preparó el audio sin que sonara», y puntuó resultado 1.

No se inventó la prueba: leyó un campo REAL cuya forma invita a esa lectura. Por eso el arreglo NO es
prohibirle mirar spans ni afirmarle la conclusión contraria — es nombrar la forma y decirle dónde está la
medida buena.
"""
from tests.use_cases.e2e.agent import judge


def _line(mech):
    for l in judge.mechanism_facts(mech).splitlines():
        if "UN SOLO evento" in l:
            return l
    return ""


AUDIT_REAL = {"n_events": 277, "n_evidence": 0, "errors": [], "tools_run": {},
              "spans": {"rail:music.playing": {"n": 1, "first_ms": 7859, "last_ms": 7859, "errors": 0}}}


def test_the_single_event_span_is_named_with_what_it_does_not_mean():
    l = _line({"audit": AUDIT_REAL})
    assert "rail:music.playing" in l
    assert "NO porque durara cero" in l
    assert "SONANDO/REPRODUCIENDO" in l, "hay que decirle dónde está la medida que sí contesta"


def test_a_span_with_several_events_says_nothing():
    """La mitad que impide que esto sea ruido: un span con duración REAL se lee como siempre."""
    au = {"n_events": 10, "n_evidence": 1, "errors": [], "tools_run": {},
          "spans": {"web:t1": {"n": 12, "first_ms": 100, "last_ms": 9000, "errors": 0}}}
    assert _line({"audit": au}) == ""


def test_it_does_not_claim_the_opposite_either():
    """No se le dice «entonces sonaba»: eso lo mide `widgets_producing`, y afirmarlo aquí sería fabricar
    un aprobado desde el arnés — el fallo simétrico y peor."""
    l = _line({"audit": AUDIT_REAL})
    assert "sonaba" not in l.lower() and "sí ocurrió" not in l


def test_without_an_audit_there_is_no_line():
    assert _line({}) == ""
