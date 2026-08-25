"""«Reseteado» tiene que ser un HECHO comprobado, no una línea que se imprime igual (2026-08-24).

Norma del operador, con cuatro hojas de casos distintos apiladas en su pantalla: *«we do one, we close, we
continue with another»*. El arnés ya reseteaba entre casos —y la observabilidad lo confirma: `session RESET`
y `widget close` salen en cada frontera— pero después hacía `time.sleep(2.0)` e imprimía «motor reseteado
(sin trabajo ni canvas anterior)» PASARA LO QUE PASARA.

Las dos mitades estaban mal:

  · los dos segundos eran un número inventado. Medido ese mismo día en la tanda de las 16:20, un worker de
    investigación del caso ANTERIOR seguía emitiendo eventos de widget después del reset;
  · y la línea es una AFIRMACIÓN, en el sitio exacto donde el operador la lee para fiarse de que el caso
    siguiente se mide solo. Una que nadie comprobaba.

Ahora se espera a que las dos señales observables —trabajo vivo y tarjetas guardadas— estén a cero, con un
TOPE (no una espera fija), y lo que se imprime es lo que se encontró. Si no queda limpio la tanda SIGUE: un
worker que tarda en morir cuesta menos que perder la medida. Lo que no puede es medirse callándolo.
"""
import inspect

from tests.use_cases.e2e.agent import probe_client as pc
from tests.use_cases.e2e.agent import run as runmod


def _viva(goal: str) -> dict:
    """Una sesión como la sirve `/api/tasks`. El `status` NO es decorado: es lo que distingue trabajo vivo de
    una fila terminada, y omitirlo en un fixture haría pasar un filtro que no filtra."""
    return {"id": "1", "status": "running", "goal": goal}


def _stub(monkeypatch, tasks_seq, items_seq):
    """Sirve una secuencia de lecturas: así se prueba que ESPERA, no solo que mira una vez."""
    t = list(tasks_seq); i = list(items_seq)
    monkeypatch.setattr(pc, "live_tasks", lambda: t.pop(0) if len(t) > 1 else t[0])
    monkeypatch.setattr(pc, "canvas_items", lambda: i.pop(0) if len(i) > 1 else i[0])


def test_vuelve_EN_CUANTO_esta_limpio(monkeypatch):
    """El presupuesto es un tope, no una espera: un motor ya limpio no puede costar 25 s por caso."""
    _stub(monkeypatch, [[]], [[]])
    st = pc.settle_after_reset(budget_s=5.0, poll_s=0.01)
    assert st["clean"] is True and st["waited_s"] < 1.0


def test_ESPERA_a_que_muera_el_trabajo_del_caso_anterior(monkeypatch):
    """La forma medida: el reset ya pasó y el worker de antes sigue vivo un momento más."""
    _stub(monkeypatch, [[_viva("el caso de antes")], [_viva("el caso de antes")], []], [[]])
    st = pc.settle_after_reset(budget_s=5.0, poll_s=0.01)
    assert st["clean"] is True, "tiene que volver a mirar, no rendirse en la primera lectura"


def test_una_TARJETA_que_sobrevive_tampoco_es_limpio(monkeypatch):
    """No basta con que muera el trabajo: una tarjeta guardada reaparece en cuanto alguien recargue."""
    _stub(monkeypatch, [[]], [[{"id": "results::abc"}]])
    st = pc.settle_after_reset(budget_s=0.05, poll_s=0.01)
    assert st["clean"] is False and st["items"] == ["results::abc"]


def test_si_no_se_limpia_DICE_QUE_QUEDO_VIVO(monkeypatch):
    """Un «no quedó limpio» sin nombres manda a mirar un log; el arnés ya tiene la respuesta en la mano."""
    _stub(monkeypatch, [[_viva("buscar un hotel en Sevilla para el finde")]], [[]])
    st = pc.settle_after_reset(budget_s=0.05, poll_s=0.01)
    assert st["clean"] is False
    assert st["tasks"] and "hotel" in st["tasks"][0]


def _codigo_del_lote() -> str:
    """El código de `_run_batch` SIN comentarios.

    Los tests de abajo buscan marcadores en la fuente, y un comentario puede TAPAR un marcador: el 2026-08-25,
    V2-328 citó la línea «motor limpio en 0.0s…» dentro de un comentario para dejar constancia del defecto, y
    los dos guardas de este fichero se pusieron rojos porque su `index()` encontró la CITA antes que el `print`.
    Ninguna conducta había cambiado. Quitar los comentarios ancla los marcadores donde importan: en el código.
    """
    return "\n".join(l for l in inspect.getsource(runmod._run_batch).splitlines()
                      if not l.strip().startswith("#"))


def test_NO_para_la_tanda_cuando_no_se_limpia():
    """Decisión explícita: se advierte y se sigue. Parar por un worker lento cuesta más que la advertencia."""
    src = _codigo_del_lote()
    i = src.index("settle_after_reset")
    tramo = src[i:i + 1200]
    assert "el motor NO quedó limpio" in tramo
    assert "break" not in tramo.split("except Exception")[0], (
        "advertir no puede convertirse en abandonar la tanda")


def test_la_linea_tranquilizadora_YA_NO_se_imprime_a_ciegas():
    """El defecto exacto: la afirmación estaba fuera de toda condición."""
    src = _codigo_del_lote()
    assert "time.sleep(2.0)" not in src, "un número inventado no es una comprobación"
    i = src.index("motor limpio en")
    # la línea buena vive DENTRO de la rama que comprobó que lo está
    assert 'if st["clean"]:' in src[:i]


def test_solo_cuenta_como_vivo_lo_que_ESTA_vivo(monkeypatch):
    """Una sesión TERMINADA en el registro no puede bloquear el arranque del caso siguiente 25 s cada vez.

    El filtro se aplica en el arnés y no se le delega al motor a propósito: `active_sessions()` estuvo sin
    filtrar hasta V2-115, y ese hueco pintó como «en curso» tareas ya acabadas. Atar la espera a un registro
    que ya falló así una vez es esperar a que vuelva a fallar."""
    monkeypatch.setattr(pc, "live_tasks", lambda: [
        {"id": "1", "status": "done", "goal": "ya terminó"},
        {"id": "3", "status": "cancelled", "goal": "parada"},
    ])
    monkeypatch.setattr(pc, "canvas_items", lambda: [])
    st = pc.settle_after_reset(budget_s=0.05, poll_s=0.01)
    assert st["clean"] is True, "done y cancelled no son trabajo vivo"


def test_una_sesion_ESPERANDO_al_operador_sigue_siendo_trabajo_vivo(monkeypatch):
    """`needs_input` es una tarea parada delante de una pregunta, no una tarea muerta: arrastra igual."""
    monkeypatch.setattr(pc, "live_tasks", lambda: [{"id": "9", "status": "needs_input", "goal": "esperando"}])
    monkeypatch.setattr(pc, "canvas_items", lambda: [])
    st = pc.settle_after_reset(budget_s=0.05, poll_s=0.01)
    assert st["clean"] is False
