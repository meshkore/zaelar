"""Confirmar una data-op IRREVERSIBLE tiene que EJECUTARLA — por voz y por botón (sesión 319252e7, 2026-08-15).

El operador: *«no funciona el borrado de la agenda»*. El registro de la sesión, entero:

    12:15:11  operador  «Pues mira, quiero que borres y limpies la agenda.»
    12:15:17  sistema   data:clear_all (mode=confirm) → pregunta
    12:15:50  operador  «Lo he confirmado yo con el botón.»      ← y la agenda seguía llena
    12:15:51  operador  «Pero sigo viendo ítems en la agenda.»
    12:16:14  sistema   data:clear_all (mode=confirm) → **la MISMA pregunta otra vez**
    12:16:16  susurro   «el sistema no ejecutó la acción real tras la confirmación, repitiendo la pregunta
                         sin avanzar»  → escala a un worker, que choca con el MISMO gate y vuelve a preguntar

La causa: `POST /widgets/{id}/confirm` solo sabía ejecutar la clase `delete`. Con una data-op devolvía
`400 acción no soportada: data` — pero `confirm.resolve()` **ya había consumido la confirmación pendiente**.
Pulsar «Sí» por tanto DESTRUÍA la mutación guardada sin ejecutar nada, y dejaba al sistema sin nada que resolver
cuando después se decía «sí» por voz: de ahí el bucle.

Lo que hizo el fallo difícil de ver es que la mitad por VOZ sí estaba completa: la misma acción funcionaba
diciendo «sí» y no funcionaba pulsando «Sí». Y ya se sabía a medias — el docstring de
`_request_cluster_confirm` (V2-086) dice que «la confirmación por BOTÓN nunca funcionó para conectar», y en vez
de arreglarlo en la fuente se movió aquel caso a otra superficie.
"""
from __future__ import annotations

import asyncio
import json
import pathlib

import pytest

ENGINE = pathlib.Path(__file__).resolve().parents[4]


@pytest.fixture
def agenda(tmp_path, monkeypatch):
    """Store AISLADO: sin esto el test le vacía la agenda REAL al operador."""
    from widgets import confirm, store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    confirm.reset()
    from widgets.agenda import data as ag
    db = ag.load_db()
    db["projects"] = [{"id": "p1", "name": "Reddit", "priority": 1, "status": "active"}]
    db["tasks"] = [{"id": "t1", "projectId": "p1", "title": "Calendario de posts", "status": "todo"}]
    db["meetings"] = [{"title": "Revisión", "date": "2026-08-15", "startTime": "17:00", "endTime": "18:00"}]
    store.save(ag.WIDGET_ID, db)
    return ag


def test_el_boton_Si_EJECUTA_la_data_op(agenda):
    """El bug exacto de la sesión: pulsar «Sí» y que la agenda siguiera llena."""
    from widgets import confirm, server_api
    confirm.request("data", "agenda", "¿Vacío la agenda entera?", op={"action": "clear_all", "payload": {}})

    res = asyncio.run(server_api.confirm_widget("agenda", {"ok": True}))
    assert json.loads(res.body)["ok"] is True, "el botón tiene que ejecutar, no devolver «acción no soportada»"

    db = agenda.load_db()
    assert db["meetings"] == [], "se confirmó y la agenda sigue con citas"
    assert all(t["status"] in ("dropped", "done") for t in db["tasks"]), "se confirmó y quedan tareas pendientes"


def test_un_Si_que_no_ejecuta_no_puede_QUEMAR_la_confirmacion(agenda):
    """Lo que convirtió un fallo en un BUCLE. Si una rama no sabe ejecutar, lo mínimo es que el operador pueda
    volver a intentarlo; antes la confirmación se consumía igual y el «sí» por voz posterior no encontraba nada
    que resolver, así que el modelo abría OTRA confirmación. Seis veces."""
    from widgets import confirm, server_api
    confirm.request("data", "agenda", "¿Vacío la agenda entera?", op={"action": "clear_all", "payload": {}})
    asyncio.run(server_api.confirm_widget("agenda", {"ok": True}))
    # Tras un «Sí» que SÍ ejecuta, la confirmación se consume — correcto. Lo que no puede pasar es lo contrario:
    # consumirla sin ejecutar. Se comprueba por su efecto, que es lo que el operador vive.
    assert not confirm.pending(), "una confirmación ya ejecutada no puede quedarse colgada"
    assert agenda.load_db()["meetings"] == []


def test_el_No_cancela_y_no_toca_nada(agenda):
    from widgets import confirm, server_api
    confirm.request("data", "agenda", "¿Vacío la agenda entera?", op={"action": "clear_all", "payload": {}})
    res = asyncio.run(server_api.confirm_widget("agenda", {"ok": False}))
    assert json.loads(res.body)["cancelled"] is True
    assert agenda.load_db()["meetings"], "un «no» no puede vaciar nada"


def test_una_confirmacion_sin_accion_guardada_no_ejecuta_a_ciegas(agenda):
    from widgets import confirm, server_api
    confirm.request("data", "agenda", "¿?", op={"action": "", "payload": {}})
    res = asyncio.run(server_api.confirm_widget("agenda", {"ok": True}))
    assert res.status_code == 400
    assert agenda.load_db()["meetings"], "sin acción declarada no se toca nada"


# ── Resolución TEMPRANA, antes del streaming (V2-090 addenda, 2026-08-15) ────────────────────────────────────────
# Sesión real f4d3c7cc: el operador dijo «Sí, vacía la entera.» y ese turno se canceló por barge-in (siguió
# hablando) antes de llegar al backstop determinista de siempre, que solo corre TRAS el streaming completo del
# modelo. La confirmación se quedó pendiente para siempre; la agenda no cambió, y NINGÚN evento de ejecución o
# cancelación quedó en el registro — la respuesta se perdió en silencio, no fue rechazada. `_resolve_pending_confirm`
# es la función que ahora se llama TEMPRANO (antes de cualquier trabajo lento) para que un sí/no claro no dependa
# de que el turno sobreviva entero. Aquí se prueba SU lógica de ejecución directamente (sin servidor HTTP), la
# misma que usa el endpoint del botón y el backstop tardío — una sola función, tres llamantes.
def test_resolve_pending_confirm_ejecuta_la_data_op(agenda):
    """La ejecución real va por `_spawn` -> `asyncio.create_task` (fire-and-forget, como en el turno de voz real):
    hace falta un loop VIVO y un tick para que el task creado corra, igual que en producción (`_run_inner` es
    una corrutina dentro del loop del agente, nunca una llamada síncrona a secas)."""
    from voice.engine.llm.providers.nucleo import _resolve_pending_confirm
    from widgets import confirm

    confirm.request("data", "agenda", "¿Vacío la agenda entera?", op={"action": "clear_all", "payload": {}})

    async def _run():
        assert _resolve_pending_confirm(True) is True
        await asyncio.sleep(0.05)   # deja correr el task fire-and-forget que despacha la mutación real

    asyncio.run(_run())

    db = agenda.load_db()
    assert db["meetings"] == [], "se confirmó y la agenda sigue con citas"
    assert all(t["status"] in ("dropped", "done") for t in db["tasks"]), "se confirmó y quedan tareas pendientes"


def test_resolve_pending_confirm_no_hace_nada_sin_confirmacion_pendiente():
    from voice.engine.llm.providers.nucleo import _resolve_pending_confirm
    from widgets import confirm

    confirm.reset()
    assert _resolve_pending_confirm(True) is False


def test_resolve_pending_confirm_adopta_el_trace_de_quien_pregunto(agenda):
    """El ask y la respuesta corren en turnos/trace distintos — sin esto el master ve DOS flujos donde el
    operador ve UNA sola acción (ver [[project_flows_board_and_trace_continuity]] de esta misma iniciativa)."""
    from voice import trace
    from voice.engine.llm.providers.nucleo import _resolve_pending_confirm
    from widgets import confirm

    trace.adopt("")
    asking_tid = trace.begin("borra toda la agenda", origin="turno")
    confirm.request("data", "agenda", "¿Vacío la agenda entera?", op={"action": "clear_all", "payload": {}})

    trace.adopt("")   # el turno de la respuesta arranca con SU PROPIO trace, como en producción

    async def _run():
        assert _resolve_pending_confirm(True) is True
        # La comprobación va DENTRO de la misma corrutina/contexto: `asyncio.run()` copia el contexto al entrar y
        # no lo propaga de vuelta al salir — igual que un turno real, donde todo esto ocurre en UNA sola cadena de
        # corrutinas sin ninguna frontera de `asyncio.run()` de por medio.
        assert trace.current() == asking_tid
        await asyncio.sleep(0.05)

    asyncio.run(_run())
    trace.adopt("")


# ── Widget voz-solo: SIN overlay visual, la voz sigue igual (2026-08-15, pedido del operador) ────────────────────
def test_confirm_ui_false_no_pinta_overlay_pero_la_confirmacion_sigue_pendiente():
    """`agenda/manifest.json` declara `confirm_ui: false` — "el widget de agenda se maneja solo con la voz". El
    registro de la confirmación (para que "sí"/"no" hablado la resuelva) tiene que ser IDÉNTICO; lo único que
    cambia es que no sale el evento `widget/confirm` que la UI usa para pintar el botón."""
    from voice.engine.llm.providers.nucleo import _confirm_ui_paints
    from voice import observer
    from widgets import confirm

    assert _confirm_ui_paints("agenda") is False

    before = len(observer.debug_events(kind="widget"))
    confirm.request("data", "agenda", "¿Vacío la agenda entera?", op={"action": "clear_all", "payload": {}},
                     notify_ui=_confirm_ui_paints("agenda"))
    after = observer.debug_events(kind="widget")
    assert len(after) == before, "confirm_ui:false no puede seguir emitiendo el evento que pinta el overlay"
    assert confirm.pending().get("agenda"), "la confirmación sigue registrada pese a no pintar overlay"


def test_confirm_ui_defaults_true_para_widgets_sin_el_flag():
    from voice.engine.llm.providers.nucleo import _confirm_ui_paints

    assert _confirm_ui_paints("meteo-soria") is True
    assert _confirm_ui_paints("no-existe-este-widget") is True


# ── La PREGUNTA que se le lee al operador ─────────────────────────────────────────────────────────────────────
def test_la_pregunta_no_recita_las_instrucciones_del_MODELO():
    """El operador oyó esto, entero, como pregunta:

        «Ojo, esto es permanente: «VACÍA la agenda entera de una vez: descarta todas las tareas pendientes,
         congela todos los proyectos y borra todas las citas y bloques. **Úsala cuando el operador pida** dejarla
         vacía «del todo»/«por completo»/«hoy y siempre», en vez de ir tirando elementos uno a uno». ¿Lo confirmo?»

    El `desc` del manifest es la descripción de la TOOL: texto escrito para el MODELO. Leérselo al operador es un
    error de categoría — le estábamos recitando nuestras instrucciones internas y pidiéndole que dijera «sí».
    """
    from voice.engine.llm.providers.nucleo import _human_confirm_question
    q = _human_confirm_question("agenda", "clear_all", {})
    assert "Úsala cuando" not in q, f"la pregunta lleva guía de uso del modelo: {q}"
    assert len(q) < 120, f"una pregunta hablada de {len(q)} chars no es una pregunta: {q}"
    # Se exige que HAYA pregunta, no que termine en «?»: «¿Vacío la agenda entera? Es permanente.» es una
    # pregunta con su aviso detrás, y eso se dice mejor en voz que al revés.
    assert "?" in q, f"tiene que preguntar algo: {q}"


def test_confirm_q_esta_declarada_donde_se_pide_confirmacion():
    """Toda acción `confirm:true` de la agenda necesita su pregunta HUMANA. Sin ella se cae al `desc`, que es lo
    que produjo el fallo de arriba."""
    man = json.loads((ENGINE / "widgets/agenda/manifest.json").read_text(encoding="utf-8"))
    sin_pregunta = [n for n, s in (man.get("actions") or {}).items()
                    if s.get("confirm") and not str(s.get("confirm_q") or "").strip()]
    assert not sin_pregunta, f"acciones que piden confirmación sin pregunta humana: {sin_pregunta}"
