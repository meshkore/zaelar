"""V2-257 — el navegador MUESTRA, la hoja GUARDA: la frontera entre las dos superficies.

LO MEDIDO, y es un fallo estructural, no de calidad de extracción: un encargo `kind:"web"` resuelve
`surface = LIST` (`nucleo.surfaces._BY_KIND`), y `LIST ∈ SHEET`, así que `dispatch._sheet_open()` ABRE la hoja de
resultados delante del operador en cuanto encarga. Y nadie escribía en ella. Los TRES caminos por los que el
navegador encuentra algo —`act_api._hand_over`, `owner._automate`, `dispatch._finalize_web`— terminaban en
`navegador.tasks.set_results()`, que escribe la TARJETA; y el prompt del worker WEB no nombraba `widget_cli` ni
`results` ni una sola vez (contado sobre el propio texto renderizado). O sea: la hoja se abría vacía por
construcción mientras los hallazgos se apilaban en la tarjeta.

Eso explica el `missing_signals: ['widget']` que el arnés reportó en V2-223 y que entonces se leyó como un fallo
de la extracción. No lo era: no había puerta. La prueba más limpia de que el nombre iba por un lado y el código
por otro es que el test de V2-223 se llama `..._lands_in_the_results_sheet` y assertaba
`tasks.get(task)["results"]`.

Lo que este fichero fija es la FRONTERA, no una pantalla:

  · la hoja ACUMULA (una hoja por encargo, N navegadores) y sabe de qué fuente vino cada cosa;
  · la tarjeta del navegador ya no publica resultados — pero la tarea SIGUE guardando el hecho, porque
    `has_results` es lo que deja al turno decir «ya trajo algo» (V2-192/V2-200), y perderlo sería una regresión;
  · los tres caminos pasan por la MISMA puerta, comprobado desde la fuente: tres copias de una regla es
    exactamente cómo se llegó a que ninguna de las tres llevara a la hoja (la lección de V2-256, una semana y
    cuatro reincidencias).
"""
import re
from pathlib import Path

import pytest

from widgets import store
from widgets.navegador import act_api, data as navdata, tasks
from widgets.results import data as sheet, intake

ENGINE = Path(__file__).resolve().parents[4]

FILA = {"title": "Fontanería Relatores", "price": "60 €", "tel": "910 00 00 00",
        "url": "https://relatores.example/", "image": "https://img.example/a.jpg"}
OTRA = {"title": "GASFONCLIMA", "tel": "911 11 11 11", "url": "https://gasfonclima.example/"}


@pytest.fixture(autouse=True)
def _hoja_aislada(tmp_path, monkeypatch):
    """La hoja del operador NO se toca: escribir en el store real le borraría lo que tiene en pantalla."""
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    store._last_hash.pop("results", None)
    yield
    store._last_hash.pop("results", None)


@pytest.fixture
def tarea():
    tid = tasks.create("Fontaneros en Madrid centro, urgencia hoy")
    act_api._HANDED.pop(tid, None)
    yield tid
    act_api._HANDED.pop(tid, None)


# ── 1) la puerta: una fila del navegador → un item de la hoja ────────────────────────────────────────────────

def test_the_row_becomes_a_sheet_item_and_the_phone_survives():
    """El esquema de item de la hoja es CERRADO y no tiene teléfono. Dejarlo caer sería el defecto de V2-240 otra
    vez: en un encargo de servicio el teléfono es el dato que RESUELVE el encargo."""
    it = intake._to_item(FILA)
    assert it["title"] == "Fontanería Relatores"
    assert it["price"] == "60 €" and it["url"] == "https://relatores.example/"
    assert {"label": "Teléfono", "value": "910 00 00 00"} in it["facts"]


def test_a_row_without_a_name_is_not_a_result():
    assert intake._to_item({"price": "60 €"}) is None
    assert intake._to_item({"title": "   "}) is None
    assert intake._to_item("no soy un dict") is None
    assert intake.push([{"price": "9 €"}]) == 0, "no hay nada que entregar; no se abre la hoja por gusto"


def test_the_sheet_ACCUMULATES_because_browsers_are_many_and_the_sheet_is_one():
    """`present` reemplaza; con dos navegadores el segundo le borraría al primero lo que encontró."""
    assert intake.push([FILA]) == 1
    assert intake.push([OTRA]) == 1
    titles = [i["title"] for i in sheet.view_data()["items"]]
    assert titles == ["Fontanería Relatores", "GASFONCLIMA"]


def test_the_same_page_extracted_twice_is_not_two_findings():
    intake.push([FILA])
    intake.push([FILA])
    assert len(sheet.view_data()["items"]) == 1


def test_where_it_came_from_travels_with_it():
    """Una fila sin origen es un rumor, y la hoja ya tiene una pestaña para eso."""
    intake.push([FILA, OTRA], source_url="https://www.google.com/search?q=fontanero")
    srcs = sheet.view_data().get("sources") or []
    assert srcs and srcs[0]["found"] == 2
    assert srcs[0]["name"] == "www.google.com", "sin nombre, el dominio identifica la fuente"


# ── 2) los TRES caminos entran por la misma puerta ───────────────────────────────────────────────────────────

def test_what_the_worker_extracts_reaches_the_SHEET(tarea):
    """El camino de V2-223, ahora contra la superficie que su propio nombre prometía."""
    act_api._hand_over(tarea, [FILA])
    assert [i["title"] for i in sheet.view_data()["items"]] == ["Fontanería Relatores"]


def test_and_the_task_still_carries_the_FACT(tarea):
    """`has_results` es lo que deja al turno decir «ya trajo algo» en vez de elegir entre «sigue viva» y «está
    bloqueada» (V2-192). El hecho se queda; lo que se fue es la superficie."""
    act_api._hand_over(tarea, [FILA])
    assert (tasks.get(tarea) or {}).get("results", {}).get("items")
    viva = [r for r in tasks.active_progress() if r["id"] == tarea]
    assert viva and viva[0]["has_results"] is True


#: Los caminos VIVOS por los que el navegador encuentra algo. `nucleo/agentes/web_cc.py` tiene un CUARTO
#: `set_results()` y no está aquí porque está APARCADO: el dispatcher enruta `kind=="web"` por el sustrato de
#: V2-038 (`dispatch._prepare_web` + `dispatch_prompts._web_prompt`) y nadie lo importa en ejecución. Es una
#: cuarta copia dormida de la misma regla, y por eso el caso de abajo la vigila en vez de ignorarla.
CAMINOS = ["widgets/navegador/act_api.py", "widgets/navegador/owner.py", "nucleo/dispatch.py"]


@pytest.mark.parametrize("rel", CAMINOS)
def test_every_path_goes_through_the_one_door(rel):
    """El guardarraíl de CABLEADO (V2-199): una puerta que no llama nadie prueba que el código compila. Y son
    justo tres ficheros porque eran tres copias de la misma regla — la forma exacta de V2-256."""
    src = (ENGINE / rel).read_text(encoding="utf-8", errors="replace")
    assert "results import intake" in src, f"{rel} encuentra cosas y no las entrega a la hoja"
    assert "intake.push" in src or "_intake.push" in src


def test_the_PARKED_fourth_copy_stays_parked():
    """Buscando los tres caminos aparecieron CUATRO `set_results()`. El cuarto (`web_cc`) está aparcado, así que
    no se cableó — pero «aparcado» es un hecho que puede dejar de serlo en silencio, y el día que alguien lo
    reviva volvería a haber un camino que encuentra cosas y no las entrega. Si este caso se pone rojo, la
    respuesta NO es borrarlo: es meter `web_cc` en CAMINOS y darle su puerta."""
    vivos = []
    for rel in ("nucleo/dispatch.py", "nucleo/workers/registry.py", "nucleo/agentes/worker.py",
                "nucleo/workers/session.py"):
        f = ENGINE / rel
        if f.exists() and "web_cc" in re.sub(r"#.*", "", f.read_text(encoding="utf-8", errors="replace")):
            vivos.append(rel)
    assert not vivos, (
        f"`web_cc` ha vuelto a estar vivo ({vivos}) y tiene su propio `set_results()` sin entrega a la hoja")


# ── 3) la tarjeta es un MONITOR ──────────────────────────────────────────────────────────────────────────────

def test_the_card_no_longer_publishes_results(tarea):
    act_api._hand_over(tarea, [FILA])
    view = navdata.view_data(tarea)
    assert "results" not in view, "la tarjeta volvió a ser una superficie de resultados"


def test_the_card_titles_itself_with_the_TASK(tarea):
    """Con varios navegadores abiertos, todos llamados «Navegador», la cabecera no identificaba ninguno."""
    tasks.set_goal_summary(tarea, "Fontaneros en Madrid centro · urgencia hoy")
    assert navdata.view_data(tarea)["title"] == "Fontaneros en Madrid centro · urgencia hoy"
    import json
    man = json.loads((ENGINE / "widgets/navegador/manifest.json").read_text(encoding="utf-8"))
    assert man.get("live_title") is True, "sin esto la cabecera del chrome sigue diciendo «Navegador»"


def test_the_state_is_three_lines_and_not_a_log(tarea):
    for txt in ("abriendo", "abriendo", "buscando", "leyendo", "extrayendo"):
        tasks.add_event(tarea, txt)
    state = navdata.view_data(tarea)["state"]
    assert state == ["buscando", "leyendo", "extrayendo"], (
        "un estado son las dos o tres últimas cosas; dieciséis eventos con su hora son un LOG, y repetir la "
        "misma línea parece progreso sin serlo")


def test_the_render_cannot_paint_results_or_a_log():
    """Desde la FUENTE, porque el contrato de datos y el render son dos sitios: quitar `results` de la vista y
    dejar el bloque que lo pinta daría una tarjeta que se queda esperando un campo que ya no llega."""
    js = (ENGINE / "widgets/navegador/widget.js").read_text(encoding="utf-8")
    for prohibido in ("data.results", "data.events", "hb-navt-item", "hb-navt-feed"):
        assert prohibido not in js, f"widget.js sigue pintando «{prohibido}»"
    assert "data.state" in js, "…y tiene que pintar el estado que sustituye a todo eso"


# ── 4) el worker sabe que la hoja existe ─────────────────────────────────────────────────────────────────────

def test_the_web_worker_prompt_names_the_sheet():
    """Contado sobre el texto RENDERIZADO, no sobre la intención: antes de V2-257 salía 0 y 0."""
    from nucleo import dispatch_prompts
    p = dispatch_prompts._web_prompt("busca fontaneros en Madrid centro", "")
    assert "widget_cli data results present" in p, "el worker no tiene forma de saber que la hoja existe"
    assert re.search(r"TARJETA[^.]*monitor", p), "…ni de saber que la tarjeta NO es donde se enseñan los hallazgos"
    assert "PRESUPUESTOS de «results»" in p, (
        "nombrar la hoja engancha sola su hoja de presupuestos (`presentation.directive_for`); si esto cae, el "
        "worker vuelve a maquetar a ciegas")


def test_a_web_errand_opens_the_sheet_in_the_first_place():
    """La otra mitad del hallazgo: la hoja ya se abría sola. Sin esto, la puerta daría a una sala cerrada."""
    from nucleo import surfaces
    assert surfaces.opens_sheet(surfaces.resolve(None, "web")), (
        "un encargo web dejó de abrir la hoja: entonces lo que entrega `intake` no lo ve nadie")
