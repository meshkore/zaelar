"""V2-259 F3 — «cierra los resultados» con dos abiertas es una PREGUNTA, no una apuesta.

Petición del operador, literal: «si hay 2 widgets de results y el usuario dice "cierra los resultados", la orden
debería generar una pregunta de: ¿cuál de las 2 búsquedas cierro, la del coche o la del fontanero?».

Es una ambigüedad de OTRO EJE que la que ya resolvía `runtime.identify()`. Aquella decide QUÉ PIEZA
(«resultados» → `results`) y pregunta cuando no hay match de nombre o alias (V2-082); ésta llega después, con la
pieza ya clara, y lo que no se sabe es CUÁL DE SUS TARJETAS. Antes no podía existir: la única pieza instanciada
era el navegador, y sus tarjetas se cierran solas al acabar la tarea. Desde V2-259 el operador tiene dos cajas
delante que se llaman igual.

Lo que se fija:

  · con una, cerrar sigue siendo cerrar — una pregunta espuria en cada cierre sería peor que el fallo que esto
    quita, así que la duda cae siempre hacia el comportamiento de siempre;
  · con dos, se pregunta nombrando los ENCARGOS y no los ids («¿results::t1 o results::t2?» no es una pregunta,
    es un volcado);
  · una pregunta que no distingue nada tampoco es una pregunta: dos hojas sin título no pueden acabar en «¿cuál
    cierro, «Resultados» o «Resultados»?»;
  · y la regla vive UNA vez, aunque este cierre se emita desde tres sitios distintos.
"""
import re
from pathlib import Path

import pytest

from widgets import instances, store
from widgets.results import data as sheet

ENGINE = Path(__file__).resolve().parents[4]
NUCLEO = ENGINE / "voice/engine/llm/providers/nucleo.py"


@pytest.fixture(autouse=True)
def _aislado(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    store._last_hash.clear()
    yield
    store._last_hash.clear()


# ── 1) con una, cerrar es cerrar ─────────────────────────────────────────────────────────────────────────────

def test_one_card_closes_without_asking():
    r = instances.resolve_close("results", ["results::t1"])
    assert r["id"] == "results::t1" and not r["ask"]


def test_none_open_still_closes_like_it_always_did():
    """Cerrar una tarjeta que ya no está es un no-op inofensivo, y era el comportamiento de siempre: el valor
    real de ese emit es cancelar la escalada espuria, no la tarjeta."""
    r = instances.resolve_close("results", [])
    assert r["id"] == "results" and not r["ask"]


def test_another_piece_is_not_ambiguous_just_because_results_has_two():
    r = instances.resolve_close("agenda", ["results::t1", "results::t2", "agenda"])
    assert r["id"] == "agenda" and not r["ask"]


def test_an_instance_named_out_loud_is_not_a_question():
    r = instances.resolve_close("results::t9", ["results::t1", "results::t2"])
    assert r["id"] == "results::t9" and not r["ask"]


# ── 2) con dos, se pregunta — y nombrando los encargos ───────────────────────────────────────────────────────

def test_two_cards_ask_which_one():
    sheet.apply_action("present", {"sheet": "t1", "title": "Fontaneros en Madrid centro",
                                   "items": [{"title": "Relatores"}]})
    sheet.apply_action("present", {"sheet": "t2", "title": "Coches de segunda mano",
                                   "items": [{"title": "Ibiza"}]})
    r = instances.resolve_close("results", ["results::t1", "results::t2"])
    assert r["id"] is None, "con dos abiertas, elegir una acierta la mitad de las veces y borra la otra mitad"
    assert "Fontaneros en Madrid centro" in r["ask"] and "Coches de segunda mano" in r["ask"]
    assert "results::" not in r["ask"], "la pregunta nombra los ENCARGOS; un id no es una pregunta"
    assert r["options"] == ["results::t1", "results::t2"]


def test_three_cards_read_as_a_list_and_not_as_a_dump():
    for n, t in enumerate(("Fontaneros", "Coches", "Hoteles"), 1):
        sheet.apply_action("present", {"sheet": f"t{n}", "title": t, "items": [{"title": "x"}]})
    ask = instances.resolve_close("results", [f"results::t{n}" for n in (1, 2, 3)])["ask"]
    assert ask.count("«") == 3 and " o «Hoteles»" in ask


def test_a_question_that_cannot_be_answered_is_not_a_question():
    """Dos hojas sin encargo detrás se titulan las dos con el relleno «Resultados». Preguntar «¿«Resultados» o
    «Resultados»?» obliga al operador a contestar algo que no distingue nada — peor que no preguntar."""
    ask = instances.resolve_close("results", ["results::t1", "results::t2"])["ask"]
    assert "«t1»" in ask and "«t2»" in ask
    assert ask.count("Resultados") == 0


def test_colliding_titles_get_disambiguated_instead_of_repeated():
    for sid in ("t1", "t2"):
        sheet.apply_action("present", {"sheet": sid, "title": "Coches", "items": [{"title": "x"}]})
    ask = instances.resolve_close("results", ["results::t1", "results::t2"])["ask"]
    assert "Coches (t1)" in ask and "Coches (t2)" in ask


# ── 3) la regla vive UNA vez ─────────────────────────────────────────────────────────────────────────────────

def test_every_close_path_goes_through_the_one_decision():
    """`nucleo.py` emite `widget/close` con id desde TRES puntos (el guard cerrar≠borrar, el backstop del turno y
    el fallback de canvas). El guardarraíl de cableado de V2-199: una decisión que no llama nadie prueba que el
    código compila. Cuarta vez esta semana que la regla estaba —o iba a quedar— repetida."""
    src = NUCLEO.read_text(encoding="utf-8", errors="replace")
    con_id = [ln for ln in src.splitlines()
              if 'emit("widget", "close"' in ln and '"id"' in ln]
    assert len(con_id) >= 3, "cambiaron los puntos de cierre: revisa que TODOS pasen por _close_target"
    for ln in con_id:
        assert '_t["id"]' in ln, f"este cierre no pasa por la decisión compartida: {ln.strip()}"
    assert src.count("def _close_target(") == 1, "la decisión tiene que estar escrita UNA vez"


def test_the_ambiguity_is_answered_by_ASKING_and_not_by_staying_silent():
    """Preguntar TAMBIÉN es haber actuado: si el fallback devolviera False, el login-fallback se llevaría el
    turno como si nadie hubiera hecho nada — el fallo que V2-023 dejó documentado."""
    src = NUCLEO.read_text(encoding="utf-8", errors="replace")
    i = src.index("def _widget_fallback(")
    cuerpo = src[i:i + 3000]
    assert "ask(_t[\"ask\"])" in cuerpo and re.search(r'ask\(_t\["ask"\]\)\s*\n(.|\n){0,400}?return True', cuerpo), (
        "preguntar tiene que contar como actuar")
    assert 'ask=lambda m: clarify.__setitem__("msg", m)' in src, (
        "el fallback no tiene por dónde preguntar: la pregunta se perdería y el cierre no ocurriría — mudo")


def test_the_raw_instances_are_readable_because_the_state_normalizes_them_away():
    """`memory.state()['open_widgets']` guarda las BASES, que es lo correcto para lo que hace: el estado del
    cerebro habla de piezas. Pero esta pregunta es sobre TARJETAS, y ahí la normalización borra justo el dato —
    el mismo colapso que V2-047 F9 anotó y nunca se cerró."""
    from server import voice_api
    voice_api.canvas_state._last_inst = None
    assert voice_api.open_instances() == [], "sin informe del canvas es «no lo sé», no una ambigüedad inventada"
    voice_api.canvas_state._last_inst = ["results::t1", "results::t2", "agenda"]
    assert instances.instances_of("results", voice_api.open_instances()) == ["results::t1", "results::t2"]
