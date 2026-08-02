"""Contrato de la SUPERFICIE GENÉRICA DE PRESENTACIÓN (`widgets/results`).

Reproduce el caso de uso que falló entero el 2026-08-02 ("busca piscinas con ambiente cerca de Tarragona y ponme
un informe con fotos en pantalla"): el operador nunca vio un resultado. Tres averías encadenadas, una por bloque:

  1. `view_data()` devolvía una lista DEMO hardcodeada de proyectos del operador (Pricewaterhouse/Mage Core/…) →
     abrir el widget para una búsqueda de piscinas pintaba "Proyectos". Una hoja en blanco no tiene contenido propio.
  2. No había forma de RELLENARLO: el único canal documentado era el tag `[[push:results]]`, que el provider de voz
     bloquea y convierte en escalada, y el widget solo declaraba la acción `choose` → un Brain Worker con los datos
     en la mano no tenía por dónde entregarlos, así que los recitaba por voz y ya.
  3. Lo pusheado era efímero: cualquier re-render volvía a `view_data()` y borraba de pantalla lo obtenido.

El test es AGNÓSTICO DEL TEMA a propósito (piscinas, coches, cuentos open-source): el widget nunca sabe de qué van
los items. Va por el MISMO camino que usa un worker (`brain_action` → `apply_action`), no por atajos.
"""
import asyncio

import pytest

from widgets import actions, runtime
from widgets.results import data as results


@pytest.fixture(autouse=True)
def _clean_sheet():
    results.apply_action("clear", {})
    yield
    results.apply_action("clear", {})


def _present(**payload):
    """Entrega por el MISMO choke point que el puente del worker (`hbwidget data results present …`)."""
    from widgets.server_api import brain_action
    return asyncio.run(brain_action("results", "present", payload))


# ── 1) hoja en blanco: sin nada entregado, NO se inventa contenido ────────────────────────────────────────
def test_empty_sheet_has_no_content_of_its_own():
    d = results.view_data()
    assert d["items"] == []
    assert d.get("note")                       # dice "sin resultados", no pinta datos de otro tema
    blob = repr(d).lower()
    for leak in ("pricewaterhouse", "mage core", "meshkore", "cryptoknight"):
        assert leak not in blob, "la superficie de presentación no puede traer datos demo propios"


# ── 2) el conjunto de resultados entra por una ACCIÓN DECLARADA, no reescribiendo el widget ───────────────
def test_present_is_a_declared_fast_action():
    man = runtime.get("results")
    assert man, "el widget results debe existir en el catálogo"
    declared = man.get("actions") or {}
    for name in ("present", "append", "clear", "choose"):
        assert name in declared, f"«{name}» debe estar DECLARADA para que el puente del worker la admita"
        # FAST = se aplica ya. Si cayera en CONFIRM, enseñar un informe pediría OK y volveríamos a la avería.
        assert actions.classify(declared[name], name) == actions.FAST


def test_worker_fills_the_sheet_through_the_bridge():
    res = _present(
        title="Piscinas con ambiente cerca de Tarragona",
        subtitle="acceso de día sin ser socio",
        items=[
            {"title": "INFINITUM Beach Club", "subtitle": "Salou · beach club", "price": "40-55€",
             "url": "https://example.com/infinitum", "image": "https://example.com/a.jpg",
             "lines": ["Day pass, 11-20h en agosto"], "primary": True},
            {"title": "Aquopolis Costa Dorada", "subtitle": "La Pineda", "price": "29€",
             "url": "https://example.com/aquopolis"},
        ])
    assert res.get("ok") and res.get("shown") == 2

    d = results.view_data()
    assert d["title"] == "Piscinas con ambiente cerca de Tarragona"
    assert [i["title"] for i in d["items"]] == ["INFINITUM Beach Club", "Aquopolis Costa Dorada"]
    top = d["items"][0]
    assert top["image"] and top["url"] and top["price"] and top["primary"] is True   # foto+enlace+precio REALES


def test_any_domain_fits_the_same_surface():
    """Nada del widget conoce el tema: el mismo contrato sirve para coches o para cuentos open-source."""
    for title, item in (
        ("Coches de segunda mano en Bilbao", {"title": "Golf GTI 2019", "price": "18.500€"}),
        ("Cuentos infantiles open-source", {"title": "The Wandering Fox", "url": "https://example.com/fox"}),
    ):
        assert _present(title=title, items=[item]).get("ok")
        d = results.view_data()
        assert d["title"] == title and d["items"][0]["title"] == item["title"]


# ── 3) lo entregado PERSISTE y se puede ir llenando en vivo ───────────────────────────────────────────────
def test_delivered_results_survive_a_re_render():
    _present(title="Informe", items=[{"title": "Uno"}, {"title": "Dos"}])
    # el canvas re-pinta llamando OTRA VEZ a view_data(): lo obtenido no puede desaparecer entre pintadas
    assert [i["title"] for i in results.view_data()["items"]] == ["Uno", "Dos"]
    assert [i["title"] for i in results.view_data()["items"]] == ["Uno", "Dos"]


def test_append_fills_progressively_and_dedups():
    _present(title="Informe", items=[{"title": "Uno", "url": "https://a"}])
    results.apply_action("append", {"items": [{"title": "Uno", "url": "https://a"},      # mismo hallazgo
                                              {"title": "Dos", "url": "https://b"}]})
    assert [i["title"] for i in results.view_data()["items"]] == ["Uno", "Dos"]
    assert results.apply_action("append", {"items": []})["ok"] is False


def test_choose_persists_the_operators_pick():
    _present(title="Informe", items=[{"title": "Uno"}, {"title": "Dos"}], choosable=True)
    assert results.apply_action("choose", {"title": "Dos"})["ok"]
    assert results.view_data()["chosen"] == "Dos"          # sobrevive al re-render, como la lista


# ── 4) el payload viene de la web abierta → esquema CERRADO ───────────────────────────────────────────────
def test_payload_schema_is_closed():
    _present(title="Informe", items=[
        {"title": "Bueno", "onclick": "alert(1)", "__proto__": "x"},
        {"subtitle": "sin título, o sea ruido"},
    ])
    items = results.view_data()["items"]
    assert len(items) == 1 and items[0]["title"] == "Bueno"
    assert "onclick" not in items[0] and "__proto__" not in items[0]


def test_unknown_action_is_refused_not_ignored():
    r = results.apply_action("rewrite_yourself", {})
    assert r["ok"] is False and "present" in r["error"]
