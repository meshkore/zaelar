"""
`clear_all` — vaciar la agenda en UNA acción (2026-08-14, sesión b70a45d0).

El operador pidió «vacía la agenda por completo, hoy y siempre» SEIS veces en cuatro minutos, y no se vació. No
era un fallo del modelo: **esta API no sabía expresar esa intención**. Solo había acciones de un elemento (`drop`
una tarea, `cancel_meeting` una cita, `drop_project` un proyecto), así que el FlashBrain solo podía tirar UNA cosa
por turno — y cada turno decía «hecho», que era verdad de la acción disparada y mentira de lo pedido:

    95,1s  data:drop            «Vacío la agenda entera: hoy y todo lo programado»   ← tiró 1 tarea
   125,4s  data:cancel_meeting  «Ya, ahora mismo lo dejo todo limpio de verdad»      ← tiró 1 cita
   191,8s  data:drop            «Hecho»                                              ← tiró 1 tarea
   230,7s  data:cancel_meeting  «Hecho»                                              ← tiró 1 cita
   238,2s  operador: «No, no está hecho, no estás comprobando que hagas las cosas»

Cuando una intención frecuente no cabe en el vocabulario declarado, el modelo no tiene forma de acertar. Estos
tests fijan que ya cabe, y que sigue exigiendo confirmación (es irreversible).
"""
from __future__ import annotations

import json
import pathlib

import pytest

ENGINE = pathlib.Path(__file__).resolve().parents[4]


@pytest.fixture
def agenda(tmp_path, monkeypatch):
    """Store AISLADO: sin esto el test le vacía la agenda REAL al operador (ver el `_DATA_DIR` inexistente del
    test de youtube, que llevaba meses escribiendo en su store de verdad)."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.agenda import data as ag
    return ag


def _poblar(ag):
    db = ag.load_db()
    db["projects"] = [{"id": "p1", "name": "Reddit", "priority": 1, "status": "active"},
                      {"id": "p2", "name": "CryptoKnight", "priority": 2, "status": "active"}]
    db["tasks"] = [{"id": "t1", "projectId": "p1", "title": "Calendario de posts", "status": "todo"},
                   {"id": "t2", "projectId": "p2", "title": "Revisión", "status": "in_progress"},
                   {"id": "t3", "projectId": "p1", "title": "Ya hecha", "status": "done"}]
    db["meetings"] = [{"title": "Calendario de posts de Reddit", "date": "2026-08-14",
                       "startTime": "10:00", "endTime": "11:00"},
                      {"title": "Revisión de CryptoKnight", "date": "2026-08-15",
                       "startTime": "17:00", "endTime": "18:00"}]
    from widgets import store
    store.save(ag.WIDGET_ID, db)
    return db


def test_clear_all_deja_la_agenda_vacia_de_verdad(agenda):
    _poblar(agenda)
    agenda.apply_action("clear_all", {})
    db = agenda.load_db()
    assert db["meetings"] == [], "quedan citas: «por completo» seguiría siendo mentira"
    assert all(t["status"] in ("dropped", "done") for t in db["tasks"]), \
        f"quedan tareas pendientes: {[t for t in db['tasks'] if t['status'] not in ('dropped', 'done')]}"
    assert all(p["status"] == "frozen" for p in db["projects"])


def test_clear_all_no_resucita_ni_pisa_lo_ya_hecho(agenda):
    """Una tarea `done` es historia del operador, no algo pendiente: se queda como estaba."""
    _poblar(agenda)
    agenda.apply_action("clear_all", {})
    hecha = next(t for t in agenda.load_db()["tasks"] if t["id"] == "t3")
    assert hecha["status"] == "done"


def test_clear_all_congela_los_proyectos_en_vez_de_borrarlos(agenda):
    """Los proyectos son la memoria de trabajo del operador. Pidió una agenda vacía, no perder de qué iba cada
    proyecto — y `frozen` es el mismo estado que ya usaba `drop_project`."""
    _poblar(agenda)
    agenda.apply_action("clear_all", {})
    db = agenda.load_db()
    assert {p["name"] for p in db["projects"]} == {"Reddit", "CryptoKnight"}, "no se borran, se congelan"


def test_clear_all_es_idempotente(agenda):
    _poblar(agenda)
    agenda.apply_action("clear_all", {})
    primera = agenda.load_db()
    agenda.apply_action("clear_all", {})
    assert agenda.load_db()["tasks"] == primera["tasks"]
    assert agenda.load_db()["meetings"] == []


def test_clear_all_sobre_una_agenda_ya_vacia_no_revienta(agenda):
    agenda.apply_action("clear_all", {})
    assert agenda.load_db()["meetings"] == []


def test_la_vista_refleja_el_vaciado(agenda):
    """Lo que se le prometió al operador es que el WIDGET se viera vacío. `view_data` es lo que pinta la tarjeta.

    FRONTERA explícita: se vacía el CONTENIDO (tareas, citas, bloques, proyectos), no el MARCO del día. La hora de
    comer sale de su horario configurado (`lunchStart`/`lunchEnd`), no de nada que él haya agendado; borrársela por
    pedir una agenda vacía le dejaría el horario roto mañana sin saber por qué. Cambiar el marco es «cambia mi
    horario», no «vacía la agenda»."""
    _poblar(agenda)
    agenda.apply_action("clear_all", {})
    d = agenda.view_data()
    contenido = [b for b in d["plan"]["blocks"] if b.get("kind") != "break"]
    assert not contenido, f"la tarjeta seguiría mostrando contenido: {contenido}"


def test_esta_declarada_y_pide_confirmacion():
    """Vaciar es IRREVERSIBLE. Y una acción que `apply_action` atiende pero el manifest no declara es INVISIBLE
    para el cerebro — o sea, no habría servido de nada."""
    from widgets import actions

    man = json.loads((ENGINE / "widgets/agenda/manifest.json").read_text(encoding="utf-8"))
    spec = (man.get("actions") or {}).get("clear_all")
    assert spec is not None, "sin declarar, el FlashBrain no puede usarla"
    assert actions.classify(spec, "clear_all") == actions.CONFIRM, "vaciar la agenda tiene que pedir un sí/no"
    assert "clear_all" in (man.get("usage") or ""), \
        "el `usage` es lo que le dice al cerebro CUÁNDO usarla en vez de ir de uno en uno"


# ── V2-473: the write does not invent — measured in `dentist-appointment-into-agenda`, round 1 ──────────────
# Four rows told the story (2026-08-29 14:19): an empty payload wrote «Cita, today, 17:00» (every field a
# DEFAULT wearing the face of success), and «date: 2026-09-08 15:00» — the model's natural datetime shape —
# kept the date but silently DROPPED the 15:00, defaulting startTime to 17:00. The operator's «a las tres de
# la tarde» never survived the write, twice, and the reply said «Hecho.» both times.


def test_a_datetime_glued_in_date_keeps_its_hour(agenda):
    A = agenda
    A.apply_action("add_meeting", {"title": "Dentista niños", "date": "2026-09-08 15:00"})
    m = [x for x in A.load_db().get("meetings", []) if x.get("title") == "Dentista niños"][-1]
    assert m["date"] == "2026-09-08" and m["startTime"] == "15:00", m
    A.apply_action("cancel_meeting", {"title": "Dentista niños"})
    # the T separator is the same natural shape
    A.apply_action("add_meeting", {"title": "Revisión", "date": "2026-09-10T09:30"})
    m = [x for x in A.load_db().get("meetings", []) if x.get("title") == "Revisión"][-1]
    assert m["date"] == "2026-09-10" and m["startTime"] == "09:30", m
    A.apply_action("cancel_meeting", {"title": "Revisión"})


def test_an_explicit_startTime_outranks_the_glued_hour(agenda):
    A = agenda
    A.apply_action("add_meeting", {"title": "Vacuna", "date": "2026-09-08 15:00", "startTime": "16:00"})
    m = [x for x in A.load_db().get("meetings", []) if x.get("title") == "Vacuna"][-1]
    assert m["startTime"] == "16:00", m
    A.apply_action("cancel_meeting", {"title": "Vacuna"})


def test_an_empty_payload_writes_nothing_and_says_why(agenda):
    A = agenda
    before = len(A.load_db().get("meetings", []))
    res = A.apply_action("add_meeting", {})
    assert len(A.load_db().get("meetings", [])) == before, "defaults must not fabricate an appointment"
    err = str((res or {}).get("error") or "")
    assert "title" in err and "date" in err and "startTime" in err, \
        f"the refusal names the expected keys so the model can retry: {res}"
