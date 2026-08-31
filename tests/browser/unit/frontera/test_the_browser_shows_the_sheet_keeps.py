"""V2-257 — the browser SHOWS, the sheet STORES: the boundary between the two surfaces.

WHAT WAS MEASURED, and it is a structural failure, not an extraction-quality issue: an errand with `kind:"web"` resolves
`surface = LIST` (`nucleo.surfaces._BY_KIND`), and `LIST ∈ SHEET`, so `dispatch._sheet_open()` OPENS the results sheet
in front of the operator as soon as the errand is created. And nobody wrote to it. The THREE paths through which the
browser finds something —`act_api._hand_over`, `owner._automate`, `dispatch._finalize_web`— ended at
`navegador.tasks.set_results()`, which writes the CARD; and the WEB worker prompt did not mention `widget_cli` or
`results` even once (counted over the rendered text itself). In other words: the sheet opened empty by
construction while findings piled up in the card.

That explains the `missing_signals: ['widget']` that the harness reported in V2-223 and that was then read as an
extraction failure. It was not: there was no door. The clearest proof that the name went one way and the code another
is that the V2-223 test is called `..._lands_in_the_results_sheet` and asserted
`tasks.get(task)["results"]`.

What this file fixes is the BOUNDARY, not a screen:

  · the sheet ACCUMULATES (one sheet per errand, N browsers) and knows which source each thing came from;
  · the browser card no longer publishes results — but the task STILL stores the fact, because
    `has_results` is what lets the turn say “it brought something back” (V2-192/V2-200), and losing it would be a regression;
  · the three paths go through the SAME door, verified from the source: three copies of a rule is
    exactly how it came about that none of the three led to the sheet (the lesson of V2-256, one week and
    four recurrences).
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
    """The operator's sheet is NOT touched: writing to the real store would erase what it has on screen."""
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


# ── 1) the door: one browser row → one sheet item ───────────────────────────────────────────────────────────

def test_the_row_becomes_a_sheet_item_and_the_phone_survives():
    """The sheet item schema is CLOSED and has no phone field. Dropping it would be the V2-240 defect all over
    again: in a service errand the phone is the data that RESOLVES the errand."""
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
    """`present` replaces; with two browsers the second would erase what the first found."""
    assert intake.push([FILA]) == 1
    assert intake.push([OTRA]) == 1
    titles = [i["title"] for i in sheet.view_data()["items"]]
    assert titles == ["Fontanería Relatores", "GASFONCLIMA"]


def test_the_same_page_extracted_twice_is_not_two_findings():
    intake.push([FILA])
    intake.push([FILA])
    assert len(sheet.view_data()["items"]) == 1


def test_where_it_came_from_travels_with_it():
    """A row without a source is a rumor, and the sheet already has a tab for that."""
    intake.push([FILA, OTRA], source_url="https://www.google.com/search?q=fontanero")
    srcs = sheet.view_data().get("sources") or []
    assert srcs and srcs[0]["found"] == 2
    assert srcs[0]["name"] == "www.google.com", "sin nombre, el dominio identifica la fuente"


# ── 2) the THREE paths enter through the same door ───────────────────────────────────────────────────────────

def test_what_the_worker_extracts_reaches_the_SHEET(tarea):
    """The V2-223 path, now against the surface its own name promised."""
    act_api._hand_over(tarea, [FILA])
    assert [i["title"] for i in sheet.view_data()["items"]] == ["Fontanería Relatores"]


def test_and_the_task_still_carries_the_FACT(tarea):
    """`has_results` is what lets the turn say “it brought something back” instead of choosing between “still alive” and “blocked”
    (V2-192). The fact remains; the surface is what went away."""
    act_api._hand_over(tarea, [FILA])
    assert (tasks.get(tarea) or {}).get("results", {}).get("items")
    viva = [r for r in tasks.active_progress() if r["id"] == tarea]
    assert viva and viva[0]["has_results"] is True


#: The LIVE paths through which the browser finds something. `nucleo/agentes/web_cc.py` has a FOURTH
#: `set_results()` and is not here because it is PARKED: the dispatcher routes `kind=="web"` through the substrate of
#: V2-038 (`dispatch._prepare_web` + `dispatch_prompts._web_prompt`) and nobody imports it at runtime. It is a
#: fourth dormant copy of the same rule, which is why the case below watches it instead of ignoring it.
CAMINOS = ["widgets/navegador/act_api.py", "widgets/navegador/owner.py", "nucleo/dispatch.py"]


@pytest.mark.parametrize("rel", CAMINOS)
def test_every_path_goes_through_the_one_door(rel):
    """The WIRING guardrail (V2-199): a door nobody calls only proves that the code compiles. And there are
    exactly three files because they were three copies of the same rule — the exact shape of V2-256."""
    src = (ENGINE / rel).read_text(encoding="utf-8", errors="replace")
    assert "results import intake" in src, f"{rel} encuentra cosas y no las entrega a la hoja"
    assert "intake.push" in src or "_intake.push" in src


def test_the_PARKED_fourth_copy_stays_parked():
    """Looking for the three paths revealed FOUR `set_results()`. The fourth (`web_cc`) is parked, so it was not
    wired — but “parked” is a fact that can silently stop being true, and the day someone revives it there would
    again be a path that finds things and does not deliver them. If this case turns red, the answer is NOT to delete
    it: put `web_cc` in PATHS and give it its door."""
    vivos = []
    for rel in ("nucleo/dispatch.py", "nucleo/workers/registry.py", "nucleo/agentes/worker.py",
                "nucleo/workers/session.py"):
        f = ENGINE / rel
        if f.exists() and "web_cc" in re.sub(r"#.*", "", f.read_text(encoding="utf-8", errors="replace")):
            vivos.append(rel)
    assert not vivos, (
        f"`web_cc` ha vuelto a estar vivo ({vivos}) y tiene su propio `set_results()` sin entrega a la hoja")


# ── 3) the card is a MONITOR ─────────────────────────────────────────────────────────────────────────────────

def test_the_card_no_longer_publishes_results(tarea):
    act_api._hand_over(tarea, [FILA])
    view = navdata.view_data(tarea)
    assert "results" not in view, "la tarjeta volvió a ser una superficie de resultados"


def test_the_card_titles_itself_with_the_TASK(tarea):
    """With several browsers open, all called “Browser”, the header identified none of them."""
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
    """From the SOURCE, because the data contract and the render are two places: removing `results` from the view and
    leaving the block that paints it would produce a card waiting for a field that no longer arrives."""
    js = (ENGINE / "widgets/navegador/widget.js").read_text(encoding="utf-8")
    for prohibido in ("data.results", "data.events", "hb-navt-item", "hb-navt-feed"):
        assert prohibido not in js, f"widget.js sigue pintando «{prohibido}»"
    assert "data.state" in js, "…y tiene que pintar el estado que sustituye a todo eso"


# ── 4) the worker knows the sheet exists ─────────────────────────────────────────────────────────────────────

def test_the_web_worker_prompt_names_the_sheet():
    """Counted over the RENDERED text, not the intention: before V2-257 both counts were 0."""
    from nucleo import dispatch_prompts
    p = dispatch_prompts._web_prompt("busca fontaneros en Madrid centro", "")
    assert "widget_cli data results present" in p, "el worker no tiene forma de saber que la hoja existe"
    assert re.search(r"TARJETA[^.]*monitor", p), "…ni de saber que la tarjeta NO es donde se enseñan los hallazgos"
    assert "PRESUPUESTOS de «results»" in p, (
        "nombrar la hoja engancha sola su hoja de presupuestos (`presentation.directive_for`); si esto cae, el "
        "worker vuelve a maquetar a ciegas")


def test_a_web_errand_opens_the_sheet_in_the_first_place():
    """The other half of the finding: the sheet was already opening by itself. Without this, the door would lead to a locked room."""
    from nucleo import surfaces
    assert surfaces.opens_sheet(surfaces.resolve(None, "web")), (
        "un encargo web dejó de abrir la hoja: entonces lo que entrega `intake` no lo ve nadie")
