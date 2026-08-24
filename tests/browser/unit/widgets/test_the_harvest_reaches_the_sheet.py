"""V2-296 — el CABLEADO de la cosecha: de quien cuenta a quien lo pinta, y qué queda cuando el encargo muere.

Hermano de `test_sheet_is_the_live_process_surface.py` y por la misma razón: el contrato de PANTALLA de la
rejilla ya está en verde (`test_harvest_grid.mjs`), pero ese fichero le pasa las cifras a mano. Lo que no puede
probar es que alguien las PRODUZCA y que lleguen — que es exactamente la forma en la que este tipo de arreglo
sale verde y no se ve nada en pantalla.

La cadena tiene cuatro eslabones y CADA UNO puede romperse solo:

  1. `tasks.tally()` acumula sobre la pestaña del navegador (la dueña de los números).
  2. `dispatch.sheet_harvest(hoja)` los SUMA sobre los encargos de esa hoja — un encargo puede abrir dos
     pestañas, y dos páginas miradas son dos vengan de donde vengan.
  3. `view_data()['harvest']` los saca por la superficie.
  4. `end_task()` los guarda, porque cuando el registro vivo desaparece la hoja se queda sin de dónde leer.

El cuarto es el que de verdad se prueba aquí. Un informe que sobrevive al encargo pero cuya explicación de
cuánto costó llegar a él se evapora cuenta la mitad de lo que pasó.
"""
import pytest

from nucleo import dispatch, surfaces
from nucleo.workers.session import SessionRecord
from widgets import store
from widgets.navegador import tasks as nav
from widgets.results import data as sheet


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    """Store, registro de sesiones y pestañas del navegador, los tres APARTE.

    El tercero no es adorno: `tasks._tasks` es un diccionario de módulo, así que una pestaña que se quede dentro
    le suma sus páginas al total del test siguiente — y un contador contaminado no falla, sale más alto, que es
    la forma de fallar más difícil de ver.
    """
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(dispatch, "_SESSIONS", {})
    monkeypatch.setattr(nav, "_tasks", {})
    store._last_hash.pop("results", None)
    yield
    store._last_hash.pop("results", None)


def _encargo(tid: str, nav_task: str, goal: str = "Busca un monitor") -> SessionRecord:
    """Un encargo VIVO con su pestaña, sellado por las mismas puertas que en producción."""
    rec = SessionRecord(task_id=tid, goal=goal, kind="web")
    surfaces.set_once(rec, "lista")
    rec.sheet = dispatch.sheet_id_for(tid)
    rec.status = "running"
    rec.nav_task = nav_task
    dispatch._SESSIONS[tid] = rec
    nav._tasks[nav_task] = {"id": nav_task, "goal": goal}
    return rec


def _harvest_en_pantalla(hoja: str) -> dict:
    """Por la MISMA puerta que la abre el canvas: `view_data` recibe la INSTANCIA como cadena (V2-259), que es
    lo que `desktop.js::show` le pasa tras partir `results::<hoja>`. La primera versión de este ayudante le daba
    un dict y salía `{}` en tres tests — sin error, porque `_safe_sheet` de un dict es una cadena rara que
    simplemente no casa con ninguna hoja. Un ayudante que llama mal a lo que mide acusa al producto."""
    return sheet.view_data(hoja).get("harvest") or {}


# ── 1) sin nada contado, «no lo sabemos» — que NO es cero ────────────────────────────────────────────────────

def test_sin_encargo_la_hoja_no_inventa_ceros():
    """`{}` y no `{pages: 0, …}`. Un cero afirma que se miró y no había; aquí no se ha mirado. La rejilla se
    apoya en esta diferencia para saber si tiene que callarse (ver `test_harvest_grid.mjs`)."""
    assert dispatch.sheet_harvest("una-hoja-cualquiera") == {}
    assert _harvest_en_pantalla("una-hoja-cualquiera") == {}


def test_un_encargo_sin_contar_todavia_tampoco_pinta_ceros():
    """El hueco de segundos entre encargar y la primera extracción. Es cuando MÁS tienta rellenar con ceros."""
    rec = _encargo("t1", "nav1")
    assert dispatch.sheet_harvest(rec.sheet) == {}


# ── 2) lo que cuenta la pestaña llega a la pantalla ──────────────────────────────────────────────────────────

def test_lo_que_cuenta_la_pestana_sale_por_la_hoja():
    rec = _encargo("t1", "nav1")
    nav.tally("nav1", pages=1, rows=40, repeated=9, unnamed=4, hollow=5, kept=22, offered=3)

    vivo = dispatch.sheet_harvest(rec.sheet)
    assert vivo["pages"] == 1 and vivo["rows"] == 40 and vivo["kept"] == 22
    assert _harvest_en_pantalla(rec.sheet) == vivo, "la hoja pinta algo distinto de lo que el registro dice"


def test_dos_paginas_del_mismo_encargo_SUMAN():
    """`tally` es acumulativo: mirar dos páginas son dos páginas, no la última."""
    rec = _encargo("t1", "nav1")
    nav.tally("nav1", pages=1, rows=40, kept=22)
    nav.tally("nav1", pages=1, rows=18, kept=7)
    vivo = dispatch.sheet_harvest(rec.sheet)
    assert (vivo["pages"], vivo["rows"], vivo["kept"]) == (2, 58, 29)


def test_dos_PESTANAS_de_la_misma_hoja_tambien_suman():
    """Un encargo puede buscar en dos sitios a la vez. Dos páginas miradas son dos vengan de donde vengan — y
    esto es lo que se rompe si alguien decide que la cosecha es «la de la pestaña activa»."""
    rec1 = _encargo("t1", "nav1")
    rec2 = SessionRecord(task_id="t2", goal="Busca un monitor", kind="web")
    surfaces.set_once(rec2, "lista")
    rec2.sheet = rec1.sheet                      # MISMA hoja: es el mismo encargo
    rec2.status = "running"
    rec2.nav_task = "nav2"
    dispatch._SESSIONS["t2"] = rec2
    nav._tasks["nav2"] = {"id": "nav2", "goal": "Busca un monitor"}

    nav.tally("nav1", pages=1, rows=40, kept=22)
    nav.tally("nav2", pages=2, rows=11, kept=4)
    vivo = dispatch.sheet_harvest(rec1.sheet)
    assert (vivo["pages"], vivo["rows"], vivo["kept"]) == (3, 51, 26)


def test_la_cosecha_de_OTRA_hoja_no_se_cuela():
    """El defecto simétrico, y el más caro: sumar de más pinta en la hoja del operador el trabajo de otro
    encargo, y eso no se ve raro — se ve como un número más alto."""
    mio = _encargo("t1", "nav1")
    otro = _encargo("t9", "nav9", goal="Busca un hotel")
    nav.tally("nav1", pages=1, rows=40, kept=22)
    nav.tally("nav9", pages=7, rows=90, kept=50)
    assert dispatch.sheet_harvest(mio.sheet)["pages"] == 1
    assert dispatch.sheet_harvest(otro.sheet)["pages"] == 7


# ── 3) el eslabón que de verdad se prueba: sobrevivir a que el encargo muera ─────────────────────────────────

def test_los_numeros_SOBREVIVEN_a_que_el_encargo_muera():
    """El caso real: se termina, el registro vivo desaparece, y la hoja se queda mirando. Sin persistir, la
    rejilla se apaga justo cuando el operador va a leer el informe — y con ella la única explicación de por qué
    el resultado es el que es."""
    rec = _encargo("t1", "nav1")
    nav.tally("nav1", pages=3, rows=40, repeated=9, unnamed=4, hollow=5, kept=22, offered=3)
    vivo = dict(dispatch.sheet_harvest(rec.sheet))

    sheet.end_task(["entrando en es.wallapop.com", "leyendo 40 fichas"], sheet=rec.sheet)
    dispatch._SESSIONS.clear()                   # el encargo MUERE: ya no hay de dónde leer en vivo
    nav._tasks.clear()

    assert dispatch.sheet_harvest(rec.sheet) == {}, "sin encargo vivo no hay lectura viva; ese es el supuesto"
    guardado = _harvest_en_pantalla(rec.sheet)
    assert guardado == vivo, "los números no sobrevivieron al encargo: la hoja se quedó sin la mitad del relato"


def test_un_encargo_que_no_conto_NADA_no_guarda_ceros():
    """La otra mitad de la misma regla. Persistir `{pages: 0, …}` es peor que no persistir: la hoja pintaría
    para siempre que se miraron cero páginas, que es una afirmación, no una ausencia."""
    rec = _encargo("t1", "nav1")
    sheet.end_task(["entrando en es.wallapop.com"], sheet=rec.sheet)
    dispatch._SESSIONS.clear()
    assert _harvest_en_pantalla(rec.sheet) == {}


def test_el_registro_VIVO_manda_sobre_lo_guardado():
    """Un encargo nuevo sobre la misma hoja tiene que pintar LO SUYO, no el recuerdo del anterior. El estado en
    dos sitios siempre acaba igual: el que se queda en pantalla es el rancio."""
    rec = _encargo("t1", "nav1")
    nav.tally("nav1", pages=3, rows=40, kept=22)
    sheet.end_task(["ya terminé"], sheet=rec.sheet)
    dispatch._SESSIONS.clear()
    nav._tasks.clear()
    assert _harvest_en_pantalla(rec.sheet)["pages"] == 3

    nuevo = _encargo("t2", "nav2")
    nuevo.sheet = rec.sheet                      # el operador vuelve a encargar sobre la misma hoja
    dispatch._SESSIONS["t2"] = nuevo
    nav.tally("nav2", pages=1, rows=5, kept=5)
    assert _harvest_en_pantalla(rec.sheet)["pages"] == 1, "la hoja sigue pintando la cosecha del encargo muerto"


# ── 4) el contador no se deja inventar claves ────────────────────────────────────────────────────────────────

def test_una_clave_que_no_existe_se_tira_en_vez_de_guardarse():
    """Una errata no puede crear un contador que ninguna superficie lee y ningún test cubre — se quedaría ahí
    sumando en silencio y el día que alguien lo pinte no habrá forma de saber desde cuándo miente."""
    rec = _encargo("t1", "nav1")
    nav.tally("nav1", pages=1, paginas=99, kept=1)
    vivo = dispatch.sheet_harvest(rec.sheet)
    assert "paginas" not in vivo and vivo["pages"] == 1
