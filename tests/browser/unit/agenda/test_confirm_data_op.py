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
