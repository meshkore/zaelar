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

from widgets import actions, runtime, store
from widgets.results import data as results


@pytest.fixture(autouse=True)
def _isolated_sheet(tmp_path, monkeypatch):
    """Store AISLADO. La primera versión de estos tests limpiaba el store REAL entre casos y le borró al operador
    el informe que tenía en pantalla en mitad de una regresión — exactamente el fallo que venimos a arreglar."""
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    store._last_hash.pop("results", None)          # el gate de "contenido idéntico" es por proceso, no por dir
    yield
    store._last_hash.pop("results", None)


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


# ── 5) "muéstrame una foto/imagen de X" — un solo item con SOLO `image`, sin url/price (2026-08-03) ─────────
# El fallo real: pedida una foto, el cerebro narraba una descripción en vez de mostrarla porque nada le decía que
# ESTO es lo que hay que rellenar (ver el fix del router en nucleo/flash/router.py). El widget en sí ya lo aceptaba.
def test_a_single_photo_request_is_a_valid_item():
    assert _present(title="Plato de quinoa", items=[{"title": "Plato de quinoa", "image": "https://example.com/quinoa.jpg"}]).get("ok")
    top = results.view_data()["items"][0]
    assert top["image"] and "url" not in top and "price" not in top


def test_several_photos_are_several_items():
    res = _present(title="Fotos de quinoa", items=[
        {"title": f"Foto {i}", "image": f"https://example.com/{i}.jpg"} for i in range(4)
    ])
    assert res.get("shown") == 4
    assert all(i.get("image") for i in results.view_data()["items"])


# ── 6) `lines` alcanza para un bloque de texto COMPLETO, no solo 4 bullets (2026-08-03) ──────────────────────
# El cap de 4 líneas bastaba para una ficha técnica pero no para "muéstrame la letra de una canción" (una canción
# real tiene decenas de versos) — otro caso real que la superficie ya podía cubrir con un tope más generoso.
def test_lines_hold_a_full_block_of_text_like_song_lyrics():
    lyrics = [f"Verso {i} de la canción" for i in range(60)]
    _present(title="Letra de una canción", items=[{"title": "Mi canción", "lines": lyrics}])
    assert results.view_data()["items"][0]["lines"] == lyrics


def test_lines_are_still_bounded_not_unlimited():
    huge = [f"línea {i}" for i in range(500)]
    _present(title="Demasiado largo", items=[{"title": "X", "lines": huge}])
    assert len(results.view_data()["items"][0]["lines"]) == results._MAX_LINES


# ── 7) PROPUESTAS COMPUESTAS: un resultado hecho de piezas (2026-08-09) ──────────────────────────────────────
# Caso del operador: "queremos ir de vacaciones… hotel + ferry", y la respuesta útil no es una lista de hoteles y
# otra de ferries, sino TRES PROPUESTAS COMPLETAS comparables entre sí. Con el esquema plano anterior eso solo se
# podía escribir disolviéndolo en prosa dentro de `lines`, que es justo lo que impide comparar.
def _plan(title="Plan A", **extra):
    it = {"title": title, "price": "1.840€ total", "parts": [
        {"kind": "Hotel", "title": "Insotel Tarida Beach", "price": "1.200€",
         "facts": {"Check-in": "15:00", "Piscinas": "3 + splash park"}},
        {"kind": "Ferry", "title": "Dénia → Ibiza", "price": "640€",
         "facts": {"Ida": "17 ago 11:30", "Vehículo": "4x4 hasta 5,0 m"}},
    ]}
    it.update(extra)
    return it


def test_one_result_can_bundle_several_pieces():
    assert _present(title="Propuestas", items=[_plan()]).get("shown") == 1
    it = results.view_data()["items"][0]
    kinds = [p["kind"] for p in it["parts"]]
    assert kinds == ["Hotel", "Ferry"], "cada pieza conserva su ROL, que es lo que hace comparables dos propuestas"
    # cada pieza lleva su PROPIO precio: sin esto el operador no puede ver de dónde sale el total
    assert [p["price"] for p in it["parts"]] == ["1.200€", "640€"]


def test_pieces_follow_the_same_closed_schema_as_items():
    _present(title="P", items=[{"title": "Plan", "parts": [
        {"kind": "Hotel", "title": "H", "onclick": "alert(1)", "script": "<script>"},
        {"kind": "Ferry", "subtitle": "pieza sin nombre = ruido"},
    ]}])
    parts = results.view_data()["items"][0]["parts"]
    assert len(parts) == 1, "una pieza sin title no se puede mostrar ni nombrar: se descarta"
    assert "onclick" not in parts[0] and "script" not in parts[0]


def test_facts_accept_the_shapes_an_llm_actually_emits():
    """`facts` lo escribe un modelo, y un modelo emite las tres formas. Las tres deben llegar ORDENADAS e iguales."""
    want = [{"label": "Desayuno", "value": "Incluido"}, {"label": "Wifi", "value": "Sí"}]
    for shape in ({"Desayuno": "Incluido", "Wifi": "Sí"},
                  [["Desayuno", "Incluido"], ["Wifi", "Sí"]],
                  [{"label": "Desayuno", "value": "Incluido"}, {"label": "Wifi", "value": "Sí"}]):
        _present(title="P", items=[{"title": "Plan", "facts": shape}])
        assert results.view_data()["items"][0]["facts"] == want, f"forma no soportada: {shape!r}"


def test_composite_payload_is_bounded():
    _present(title="P", items=[{"title": "Plan",
                                "parts": [{"kind": "K", "title": f"p{i}"} for i in range(20)],
                                "images": [f"https://e.com/{i}.jpg" for i in range(40)],
                                "facts": {f"k{i}": f"v{i}" for i in range(90)}}])
    it = results.view_data()["items"][0]
    assert len(it["parts"]) == results._MAX_PARTS
    assert len(it["images"]) == results._MAX_IMAGES
    assert len(it["facts"]) == results._MAX_FACTS


# ── 8) SEGUNDA PÁGINA: "enséñame en detalle la propuesta uno" ────────────────────────────────────────────────
def test_detail_and_list_are_declared_fast_actions():
    declared = (runtime.get("results") or {}).get("actions") or {}
    for name in ("detail", "list"):
        assert name in declared, f"«{name}» debe estar DECLARADA para que el cerebro pueda invocarla"
        assert actions.classify(declared[name], name) == actions.FAST


def test_detail_by_ordinal_because_that_is_how_voice_refers_to_it():
    """Por VOZ el operador dice «la propuesta número uno», no el nombre comercial del hotel: el ordinal sobrevive
    al STT mucho mejor que «Insotel Tarida Beach», así que la acción tiene que aceptarlo."""
    _present(title="Propuestas", items=[_plan("Plan A"), _plan("Plan B")])
    assert results.apply_action("detail", {"index": 2}).get("detail") == "Plan B"
    d = results.view_data()
    assert d["view"] == "detail" and d["focus"] == "Plan B"


def test_detail_by_name_tolerates_a_partial_title():
    _present(title="Propuestas", items=[_plan("Plan A — Ibiza en familia")])
    assert results.apply_action("detail", {"title": "ibiza"}).get("ok") is True


def test_list_goes_back_to_the_grid():
    _present(title="Propuestas", items=[_plan()])
    results.apply_action("detail", {"index": 1})
    results.apply_action("list", {})
    d = results.view_data()
    assert "view" not in d and "focus" not in d


def test_detail_of_something_not_there_is_refused_not_guessed():
    _present(title="Propuestas", items=[_plan("Plan A")])
    r = results.apply_action("detail", {"title": "un hotel que nunca buscamos"})
    assert r["ok"] is False
    assert results.view_data().get("view") is None, "un fallo no puede dejar la hoja en una página que no existe"


def test_emptying_the_sheet_drops_a_stale_detail_page():
    """Si el detalle sobreviviera a un `present` que ya no trae ese item, la hoja apuntaría a un resultado
    inexistente — pantalla en blanco sin explicación."""
    _present(title="Propuestas", items=[_plan("Plan A")])
    results.apply_action("detail", {"index": 1})
    _present(title="Otra búsqueda", items=[])
    assert results.view_data().get("view") is None


# ── 9) el cerebro SABE lo que hay en pantalla (prompt_digest) ────────────────────────────────────────────────
# Sin esto, preguntado "¿el hotel de la propuesta 2 tiene wifi?" —un dato ESCRITO en la tarjeta que el operador
# está mirando— el cerebro tenía que adivinar o escalar una búsqueda nueva para recuperar algo que ya poseía.
def test_digest_carries_the_hard_facts_so_followups_need_no_new_search():
    _present(title="Propuestas", items=[
        _plan("Plan A", facts={"Wifi": "Sí, gratis"}),
        _plan("Plan B", facts={"Wifi": "De pago, 5€/día"}),
    ])
    dig = results.prompt_digest()
    assert "#1" in dig and "#2" in dig, "el ordinal tiene que estar: es como el operador se refiere a cada una"
    assert "Sí, gratis" in dig and "De pago, 5€/día" in dig
    assert "Check-in: 15:00" in dig, "los datos de cada PIEZA también, no solo los del conjunto"


def test_digest_says_the_sheet_is_empty_instead_of_staying_silent():
    assert "VAC" in results.prompt_digest().upper()


def test_digest_is_bounded_even_with_a_huge_result_set():
    from widgets import refs
    _present(title="P", items=[_plan(f"Plan {i}", lines=[f"detalle {j}" * 20 for j in range(30)])
                               for i in range(40)])
    assert len(refs.prompt_digest("results")) <= refs._MAX_DIGEST_CHARS + 80


def test_digest_is_reached_through_the_generic_hook_not_a_special_case():
    """`widgets/brief.py` no puede conocer al widget «results»: el digest se recoge por el hook genérico, así que
    cualquier widget futuro que lo implemente aparece sin tocar el puente."""
    from widgets import refs
    _present(title="Propuestas", items=[_plan("Plan A")])
    assert refs.prompt_digest("results").startswith("#1")
    assert refs.prompt_digest("agenda") == "" or isinstance(refs.prompt_digest("agenda"), str)


# ══ 10) LAS OTRAS TRES PESTAÑAS (2026-08-12) ═══════════════════════════════════════════════════════════════════
# Norma del operador: esta superficie se va a usar para MUCHAS búsquedas complejas, y una búsqueda compleja no es
# solo su resultado — es también con qué criterio se hizo, cómo va y de dónde salen los datos. Esas tres cosas
# solo existían de palabra (había que preguntárselas al agente), así que no se podían comprobar.
import pathlib

WIDGET_JS = pathlib.Path("widgets/results/widget.js")


def test_the_four_tabs_are_declared_fast_actions():
    declared = (runtime.get("results") or {}).get("actions") or {}
    for name in ("tab", "sources", "progress", "criteria"):
        assert name in declared, f"«{name}» debe estar DECLARADA para que el puente del worker la admita"
        assert actions.classify(declared[name], name) == actions.FAST


def test_the_open_tab_lives_in_the_payload_so_voice_can_drive_it():
    """Como `view`/`focus`: la pestaña NO es estado del navegador. Si lo fuera, «enséñame de dónde has sacado
    esto» no podría mover la pantalla y una recarga perdería dónde estaba mirando el operador."""
    _present(title="P", items=[{"title": "Uno"}])
    assert results.apply_action("tab", {"tab": "sources"})["ok"]
    assert results.view_data()["tab"] == "sources"


def test_the_tab_name_survives_coming_from_voice():
    """Llega por STT y en el idioma del operador. Normalizar el argumento que el modelo YA eligió es el mismo
    papel que juega el ordinal en `detail` — no es una tabla de intención."""
    for said in ("fuentes", "Fuentes", "webs"):
        assert results.apply_action("tab", {"tab": said})["tab"] == "sources"
    assert results.apply_action("tab", {"tab": "resumen"})["tab"] == "summary"
    assert results.apply_action("tab", {"tab": "criterios"})["tab"] == "criteria"


def test_an_unknown_tab_is_refused_not_guessed():
    r = results.apply_action("tab", {"tab": "chorradas"})
    assert r["ok"] is False and "sources" in r["error"]


def test_leaving_the_results_tab_closes_the_detail_page():
    """Si el detalle sobreviviera a un cambio de pestaña, volver a «Resultados» pintaría un expediente en vez de
    la lista que el operador espera."""
    _present(title="P", items=[_plan("Plan A")])
    results.apply_action("detail", {"index": 1})
    results.apply_action("tab", {"tab": "sources"})
    d = results.view_data()
    assert d["tab"] == "sources" and "view" not in d


# ── FUENTES: lo que convierte «no encontré nada» en un dato auditable ─────────────────────────────────────────
def test_a_source_records_what_happened_there_not_just_that_it_was_visited():
    assert results.apply_action("sources", {"sources": [
        {"name": "Wallapop", "url": "https://es.wallapop.com", "status": "auth",
         "detail": "pedía iniciar sesión para ver los anuncios"},
        {"name": "Cosasdebarcos", "url": "https://cosasdebarcos.com", "status": "partial",
         "detail": "el listado corta a 50", "found": 50},
        {"name": "Yachtworld", "url": "https://yachtworld.es", "status": "ok", "found": 128},
    ]})["sources"] == 3
    src = {s["name"]: s for s in results.view_data()["sources"]}
    assert src["Wallapop"]["status"] == "auth" and src["Wallapop"]["detail"]
    assert src["Cosasdebarcos"]["found"] == 50
    c = results.view_data()["counts"]
    assert c["sources_failed"] == 1 and c["from_sources"] == 178


def test_reporting_the_same_source_twice_updates_it_instead_of_duplicating():
    """Una fuente se anuncia al entrar y se cierra al salir. Si cada reporte creara una fila, la pestaña sería un
    log en vez del ESTADO de cada sitio."""
    results.apply_action("sources", {"sources": [{"name": "Yachtworld", "url": "https://yachtworld.es",
                                                  "status": "pending"}]})
    results.apply_action("sources", {"sources": [{"name": "Yachtworld", "url": "https://yachtworld.es",
                                                  "status": "ok", "found": 128}]})
    src = results.view_data()["sources"]
    assert len(src) == 1 and src[0]["status"] == "ok" and src[0]["found"] == 128


def test_an_unknown_source_status_degrades_instead_of_leaking_through():
    results.apply_action("sources", {"sources": [{"name": "X", "status": "<script>"}]})
    assert results.view_data()["sources"][0]["status"] in results._SOURCE_STATUS


def test_a_source_with_no_name_takes_it_from_the_domain():
    results.apply_action("sources", {"sources": [{"url": "https://www.yachtworld.es/veleros"}]})
    assert results.view_data()["sources"][0]["name"] == "www.yachtworld.es"


def test_sources_are_refused_when_there_is_nothing_to_record():
    assert results.apply_action("sources", {"sources": [{"status": "ok"}]})["ok"] is False


# ── SUMARIO: lo reportado y lo derivado, separados ────────────────────────────────────────────────────────────
def test_the_summary_never_passes_off_card_count_as_breadth():
    """«Cuántos ha explorado» solo lo sabe quien trabajó. Sin reportar, la hoja lo DICE en vez de enseñar el
    número de tarjetas como si fuera la amplitud — que es justo el conformismo que el brief existe para evitar."""
    _present(title="P", items=[{"title": f"R{i}"} for i in range(3)])
    c = results.view_data()["counts"]
    assert c["shown"] == 3 and c["explored"] is None
    results.apply_action("progress", {"explored": 47})
    assert results.view_data()["counts"]["explored"] == 47


def test_progress_merges_and_accumulates_the_steps():
    results.apply_action("progress", {"state": "barriendo", "steps": ["portal 1"]})
    results.apply_action("progress", {"state": "filtrando", "explored": 20, "steps": ["portal 2"]})
    s = results.view_data()["summary"]
    assert s["state"] == "filtrando" and s["explored"] == 20
    assert s["steps"] == ["portal 1", "portal 2"], "los hitos se acumulan; el estado se reemplaza"


def test_the_same_step_repeated_is_not_progress():
    results.apply_action("progress", {"steps": ["mirando"]})
    results.apply_action("progress", {"steps": ["mirando"]})
    assert results.view_data()["summary"]["steps"] == ["mirando"]


def test_progress_is_refused_when_it_says_nothing():
    assert results.apply_action("progress", {})["ok"] is False


# ── CRITERIOS: el encargo tal y como se ejecuta, corregible por voz ───────────────────────────────────────────
def test_criteria_hold_the_brief_and_accumulate_the_operators_corrections():
    results.apply_action("criteria", {"goal": "velero de segunda mano", "hard": ["eslora 40-50 pies"]})
    results.apply_action("criteria", {"changes": ["que sean de 42 a 49 pies"]})
    results.apply_action("criteria", {"changes": ["y con motor diésel"]})
    c = results.view_data()["criteria"]
    assert c["goal"] == "velero de segunda mano" and c["hard"] == ["eslora 40-50 pies"]
    assert c["changes"] == ["que sean de 42 a 49 pies", "y con motor diésel"]


def test_a_correction_does_not_wipe_the_work_in_progress():
    """Corregir un criterio a mitad de camino NO puede tirar lo ya encontrado: el operador está afinando, no
    empezando otra cosa."""
    results.apply_action("criteria", {"goal": "velero de segunda mano"})
    _present(title="Veleros", items=[{"title": "Bavaria 46"}])
    results.apply_action("sources", {"sources": [{"name": "Yachtworld", "status": "ok"}]})
    results.apply_action("criteria", {"changes": ["de 42 a 49 pies"]})
    d = results.view_data()
    assert [i["title"] for i in d["items"]] == ["Bavaria 46"] and len(d["sources"]) == 1


def test_a_different_goal_is_a_different_investigation_and_clears_the_stale_sheet():
    """El operador ya se comió una vez quedarse mirando los resultados de la búsqueda ANTERIOR creyendo que eran
    los suyos. El objetivo es la firma del encargo: si cambia, la hoja se vacía."""
    results.apply_action("criteria", {"goal": "velero de segunda mano"})
    _present(title="Veleros", items=[{"title": "Bavaria 46"}])
    results.apply_action("sources", {"sources": [{"name": "Yachtworld", "status": "ok"}]})
    results.apply_action("progress", {"explored": 40})
    assert results.apply_action("criteria", {"goal": "pisos en Tarragona"})["reset"] is True
    d = results.view_data()
    assert d["items"] == [] and d["sources"] == [] and d["summary"] == {}
    assert d["criteria"]["goal"] == "pisos en Tarragona"


def test_the_goal_becomes_a_headline_not_a_paragraph():
    """Visto en vivo el 2026-08-12: el `goal` del brief es un párrafo autocontenido («…y reportar el estado de
    cada fuente consultada»). Puesto crudo como título ocupaba cinco líneas antes de enseñar un solo resultado.
    El texto íntegro sigue completo en la pestaña CRITERIOS, que es su sitio."""
    goal = ("Encontrar los mejores veleros de segunda mano a la venta ahora mismo que cumplan: precio ≤ 50.000 €, "
            "eslora ≤ 20 m, listos para navegar, con amarre en Mediterráneo y motor en buen estado")
    results.apply_action("criteria", {"goal": "algo anterior"})
    results.apply_action("criteria", {"goal": goal})
    d = results.view_data()
    from widgets import presentation
    assert len(d["title"]) <= presentation.contract("results")["sheet_title"] + 1
    assert d["criteria"]["goal"] == goal, "recortar el TÍTULO no puede recortar el criterio"


def test_a_second_round_keeps_the_same_goal_so_it_never_clears():
    """«No me convence, sigue buscando» sube la amplitud sobre el MISMO objetivo (research.expand). Si eso
    limpiara la hoja, continuar una búsqueda borraría lo que llevaba encontrado."""
    results.apply_action("criteria", {"goal": "velero de segunda mano"})
    _present(title="Veleros", items=[{"title": "Bavaria 46"}])
    r = results.apply_action("criteria", {"goal": "velero de segunda mano", "min_candidates": 60})
    assert r["reset"] is False
    assert results.view_data()["items"], "una ronda 2 no puede vaciar la hoja"


def test_present_preserves_the_other_three_tabs():
    """Un trabajo largo hace varios `present` (provisional → final). Borrar en cada uno las fuentes y el sumario
    ya reportados perdería datos que costaron minutos de navegación."""
    results.apply_action("criteria", {"goal": "veleros"})
    results.apply_action("sources", {"sources": [{"name": "Yachtworld", "status": "ok", "found": 128}]})
    results.apply_action("progress", {"explored": 47})
    _present(title="Veleros · selección final", items=[{"title": "Bavaria 46"}])
    d = results.view_data()
    assert d["sources"] and d["summary"]["explored"] == 47 and d["criteria"]["goal"] == "veleros"


def test_clear_wipes_every_tab():
    results.apply_action("criteria", {"goal": "veleros"})
    results.apply_action("sources", {"sources": [{"name": "Yachtworld", "status": "ok"}]})
    results.apply_action("clear", {})
    d = results.view_data()
    assert d["items"] == [] and d["sources"] == [] and d["criteria"] == {} and d["summary"] == {}


# ── el cerebro VE las tres pestañas, así que responde sin volver a buscar ─────────────────────────────────────
def test_digest_carries_the_sources_so_why_didnt_you_find_it_has_an_answer():
    results.apply_action("criteria", {"goal": "velero de 42-49 pies", "hard": ["eslora 42-49 pies"]})
    results.apply_action("sources", {"sources": [
        {"name": "Wallapop", "status": "auth", "detail": "pedía iniciar sesión"}]})
    results.apply_action("progress", {"state": "verificando finalistas", "explored": 47})
    dig = results.prompt_digest()
    assert "Wallapop" in dig and "autenticación" in dig
    assert "47 explorados" in dig and "verificando finalistas" in dig
    assert "eslora 42-49 pies" in dig


def test_digest_of_an_empty_sheet_still_shows_the_criteria_being_worked_on():
    """El caso de los primeros dos minutos: aún no hay ni un resultado, pero el cerebro ya puede contar con qué
    se está buscando en vez de decir que no sabe nada."""
    results.apply_action("criteria", {"goal": "velero de segunda mano"})
    dig = results.prompt_digest()
    assert "velero de segunda mano" in dig and "VAC" in dig.upper()


def test_digest_stays_bounded_with_every_tab_full():
    from widgets import refs
    results.apply_action("criteria", {"goal": "x" * 300, "hard": ["h" * 200] * 14, "soft": ["s" * 200] * 14})
    results.apply_action("sources", {"sources": [
        {"name": f"fuente {i}", "status": "ok", "detail": "d" * 200, "found": i} for i in range(40)]})
    _present(title="P", items=[_plan(f"Plan {i}") for i in range(40)])
    assert len(refs.prompt_digest("results")) <= refs._MAX_DIGEST_CHARS + 80


# ══ 11) FICHA DINÁMICA: cada tipo de resultado se enseña distinto, SIN aceptar HTML ════════════════════════════
def test_a_card_can_be_composed_of_blocks():
    _present(title="Veleros", items=[{"title": "Bavaria 46", "blocks": [
        {"kind": "facts", "title": "Ficha técnica", "facts": {"Eslora": "14,27 m", "Motor": "Volvo 75cv"}},
        {"kind": "chips", "chips": ["Piloto automático", "Radar", "Watermaker"]},
        {"kind": "meter", "title": "Estado del casco", "value": 8, "max": 10, "caption": "osmosis tratada"},
        {"kind": "table", "columns": ["Año", "Precio"], "rows": [["2019", "185.000 €"], ["2018", "172.000 €"]]},
        {"kind": "section", "title": "Documentación", "blocks": [{"kind": "link", "url": "https://e.com/x",
                                                                  "label": "Informe de tasación"}]},
    ]}])
    kinds = [b["kind"] for b in results.view_data()["items"][0]["blocks"]]
    assert kinds == ["facts", "chips", "meter", "table", "section"]


def test_html_is_not_a_block_kind():
    """El payload viene de la web abierta. Un `kind` desconocido se DESCARTA entero — no se degrada a texto, que
    sería colar contenido de un tercero por otra puerta."""
    _present(title="P", items=[{"title": "X", "blocks": [
        {"kind": "html", "html": "<img src=x onerror=alert(1)>"},
        {"kind": "raw", "text": "<script>alert(1)</script>"},
        {"kind": "text", "lines": ["esto sí"]},
    ]}])
    blocks = results.view_data()["items"][0]["blocks"]
    assert [b["kind"] for b in blocks] == ["text"]


def test_blocks_are_bounded_and_nest_only_one_level():
    _present(title="P", items=[{"title": "X", "blocks":
        [{"kind": "text", "lines": ["l"]} for _ in range(40)]
        + [{"kind": "section", "blocks": [{"kind": "section", "blocks": [{"kind": "text", "lines": ["hondo"]}]}]}]}])
    blocks = results.view_data()["items"][0]["blocks"]
    assert len(blocks) <= results._MAX_BLOCKS
    _present(title="P", items=[{"title": "X", "blocks": [
        {"kind": "section", "blocks": [{"kind": "section", "blocks": [{"kind": "text", "lines": ["hondo"]}]}]}]}])
    assert results.view_data()["items"][0].get("blocks") in (None, []), "un árbol no es una ficha"


def test_an_empty_block_is_dropped_instead_of_painting_a_hole():
    _present(title="P", items=[{"title": "X", "blocks": [
        {"kind": "chips", "chips": []}, {"kind": "table", "rows": []}, {"kind": "link"}]}])
    assert "blocks" not in results.view_data()["items"][0]


# ── LA VALORACIÓN: estaba en el esquema desde hace meses y no se pintaba en ningún sitio ──────────────────────
def test_the_score_accepts_the_shapes_a_researcher_actually_writes():
    for raw, want in ((8.7, 8.7), ("8,7/10", 8.7), ({"value": 87, "max": 100}, 87)):
        _present(title="P", items=[{"title": "X", "score": raw}])
        assert results.view_data()["items"][0]["score"]["value"] == want


def test_a_score_carries_its_why_because_a_mark_alone_cannot_be_argued_with():
    _present(title="P", items=[{"title": "X", "score": {"value": 8.7, "why": "buen estado, precio ajustado"}}])
    s = results.view_data()["items"][0]["score"]
    assert s["why"] == "buen estado, precio ajustado" and s["max"] == 10


def test_a_non_numeric_grade_still_works_as_a_label():
    _present(title="P", items=[{"title": "X", "score": "Excelente"}])
    assert results.view_data()["items"][0]["score"] == {"label": "Excelente"}


def test_a_garbage_score_is_dropped_not_painted_as_zero():
    for junk in ("", None, [], {"nada": 1}, float("nan")):
        _present(title="P", items=[{"title": "X", "score": junk}])
        assert "score" not in results.view_data()["items"][0], f"con {junk!r} no hay valoración que enseñar"


def test_the_detail_page_shows_the_score_and_the_dynamic_card():
    """Contrato de render (los tests de frontend son de string): el operador pidió que el expediente incluyera
    «la valoración y todos los datos de la ficha»."""
    src = WIDGET_JS.read_text()
    assert "function scoreBlock(" in src
    assert "scoreBlock(it.score)" in src, "la valoración tiene que salir en el DETALLE, no solo en la tarjeta"
    assert "renderBlocks(it.blocks)" in src, "la ficha a medida también se despliega en el detalle"


# ══ 12) es una superficie DE SERIE, no un widget que se hizo el usuario ════════════════════════════════════════
def test_the_sheet_ships_with_the_product():
    """Estaba en la lista curada `_BUILTINS` y a la vez su manifest declaraba `origin:"user"` — y el explícito
    manda, así que Config la listaba como «tuyo». Es la superficie con la que zaelar entrega CUALQUIER búsqueda:
    de serie. (Sigue siendo un widget full-stack a propósito: es su `data.py` + acciones declaradas lo que permite
    que un Brain Worker la rellene; una superficie nativa del frontend no tendría por dónde recibir los datos.)"""
    from widgets import registry
    man = runtime.get("results") or {}
    assert registry.origin_of(man) == "builtin"
    assert "results" in registry._BUILTINS


# ══ 13) el DIGEST cabe en el prompt sin comerse los resultados ══════════════════════════════════════════════════
def test_the_head_never_squeezes_the_results_out_of_the_digest():
    """El encabezado (sumario+fuentes+criterios) va DELANTE, así que sin techo propio unos criterios largos
    empujarían los resultados fuera del recorte: el cerebro sabría con qué se busca pero no qué se ha encontrado,
    que es exactamente al revés de lo útil."""
    results.apply_action("criteria", {"goal": "velero " + "x" * 400,
                                      "hard": [f"duro {i} " + "y" * 200 for i in range(14)],
                                      "changes": [f"corrección {i} " + "z" * 200 for i in range(14)]})
    results.apply_action("sources", {"sources": [
        {"name": f"fuente {i}", "status": "auth", "detail": "d" * 200, "found": i} for i in range(40)]})
    _present(title="P", items=[{"title": f"Resultado {i}", "price": f"{i}.000 €"} for i in range(12)])
    head = results._digest_head(results.view_data())
    assert len(head) <= results._MAX_HEAD_CHARS
    dig = results.prompt_digest()
    assert "#1 Resultado 0" in dig, "los resultados tienen que sobrevivir al recorte del encabezado"


def test_when_the_head_is_squeezed_it_keeps_the_sources_and_drops_the_criteria():
    """Orden por IRREEMPLAZABILIDAD: el estado de una fuente solo lo sabe esta pantalla; los criterios se dijeron
    en voz alta y el cerebro los tiene en la conversación reciente. Recortar el criterio se puede permitir."""
    results.apply_action("criteria", {"goal": "g" * 300, "hard": ["h" * 200] * 14})
    results.apply_action("sources", {"sources": [
        {"name": "Wallapop", "status": "auth", "detail": "pedía iniciar sesión"}]})
    head = results._digest_head(results.view_data())
    assert "Wallapop" in head and "autenticación" in head


def test_failed_sources_lead_because_they_are_the_ones_that_change_an_answer():
    results.apply_action("sources", {"sources": [
        {"name": "BienA", "status": "ok", "found": 10},
        {"name": "BienB", "status": "ok", "found": 20},
        {"name": "Wallapop", "status": "auth", "detail": "pedía sesión"},
    ]})
    head = results._digest_head(results.view_data())
    assert head.index("Wallapop") < head.index("BienA")


# ══ 14) LA VISTA: la lista se BARRE, el expediente se LEE (2026-08-12, visto en pantalla) ═══════════════════════
# Con las fichas pintando todos sus bloques, UNA tarjeta llenaba la hoja entera — y desde que la entrega por defecto
# son diez resultados, eso convierte la lista en algo que no se puede recorrer. Contratos de render (los tests de
# frontend son de string): en la lista van los bloques LIGEROS; los pesados son lo que uno va a buscar al abrir.
def test_the_list_shows_a_summary_card_not_the_whole_dossier():
    src = WIDGET_JS.read_text()
    assert "renderBlocks(blocks, {compact: true})" in src, "la LISTA pinta la ficha en modo compacto"
    assert "renderBlocks(it.blocks)" in src, "y el EXPEDIENTE, entera"
    assert "const LIGHT_BLOCKS = new Set([\"chips\"])" in src
    assert 'b.kind === "text" && b.tone === "warn"' in src, \
        "un AVISO no puede quedarse escondido detrás de un clic (regla de presentación)"


def test_the_badge_travels_with_the_title_not_with_the_button():
    """«Mejor conjunto» CALIFICA el resultado. Al pie acababa junto a «Ver detalle» y se leía como otro botón."""
    src = WIDGET_JS.read_text()
    assert "hr-metarow" in src
    i_meta, i_more = src.index("hr-metarow"), src.index('elem("button","hr-more"')
    assert i_meta < i_more


def test_the_numbers_that_get_compared_are_tabular():
    """Detalle de composición, no capricho: en una superficie cuyo trabajo es poner precios y notas unos debajo de
    otros, dígitos de anchura distinta obligan a releer para saber cuál es mayor."""
    src = WIDGET_JS.read_text()
    i = src.index("font-variant-numeric:tabular-nums")
    block = src[max(0, i - 400):i]
    for cls in ("hr-price", "hr-score", "hr-stat b", "hr-sn", "hr-tbl td"):
        assert cls in block, f"{cls} lleva cifras que se comparan: van tabulares"


def test_the_type_scale_and_spacing_are_a_system_not_ad_hoc_numbers():
    """La versión anterior acumulaba trece tamaños de letra y márgenes elegidos uno a uno. Eso no se lee como una
    superficie, se lee como parches. Un techo de magnitudes crudas obliga a usar la escala."""
    src = WIDGET_JS.read_text()
    css = src[src.index("s.textContent=`"):src.index("`; document.head.appendChild(s)")]
    for token in ("--f-body", "--f-micro", "--s3", "--r-md", "--line:"):
        assert token in css, f"falta el token {token} de la escala"
    import re
    # Magnitudes crudas EN USO, excluyendo la definición de los propios tokens (ahí los px son obligatorios) y los
    # valores por debajo de 4px (hilos, semitonos ópticos: no hay escala que los cubra sin quedar peor).
    body = "\n".join(ln for ln in css.split("\n") if not re.match(r"\s*--[a-z0-9-]+:", ln))
    raw = [m for m in re.findall(r":\s*(\d+(?:\.\d+)?)px", body) if float(m) > 3]
    # 26 y no menos: lo que queda son alturas de imagen (128/168/100/62) y desplazamientos ópticos de 4-7px, que son
    # one-offs estructurales de verdad — meterlos en la escala sería rigor de mentira. El techo está para que un
    # TAMAÑO DE LETRA o un margen no vuelvan a escaparse: ya pasó, y con la escala nueva el título de la ficha
    # destacada se quedó en 15.5px, o sea MÁS PEQUEÑO que el normal. Un número fuera de la escala no se entera de
    # que la escala cambió.
    assert len(raw) <= 26, (f"demasiadas magnitudes crudas en uso ({len(raw)}: {sorted(set(raw))}): "
                            "usa la escala --s*/--f*/--r*")
    css_fonts = re.findall(r"font-size:\s*(\d+(?:\.\d+)?)px", body)
    assert not css_fonts, f"todo tamaño de letra sale de la escala --f-*; crudos: {css_fonts}"
    assert "#0d1622" in css or "#e8edf5" in css, "los hex solo valen como FALLBACK de var(--hb-*)"
    assert "color:#" not in css.replace("color:#fff", ""), "ningún color fuera del contrato --hb-*"


# ══ 15) LA CABECERA DICE LA TAREA, NO EL NOMBRE DE LA PIEZA (2026-08-12) ════════════════════════════════════════
# Norma del operador, literal: «no hace falta que la gente sepa que eso es el visor o que eso es la muestra de
# resultados, sino es lo que le hemos pedido puesto ahí». En una superficie GENÉRICA el nombre del catálogo
# («Resultados») no identifica nada — lo que identifica esa tarjeta es el ENCARGO que está mostrando.
DESKTOP_JS = pathlib.Path("frontend/app/widgets/desktop.js")


def test_the_sheet_opts_into_a_live_title():
    """Opt-in POR WIDGET, no global: el reloj o la agenda sí se identifican por su nombre, y cambiárselo a todos
    sería una regresión."""
    man = runtime.get("results") or {}
    assert man.get("live_title") is True
    assert "live_title" in pathlib.Path("widgets/server_api.py").read_text(), \
        "el canvas lo necesita del índice compacto, antes de pedir el manifest entero"


def test_the_canvas_puts_the_task_in_the_card_header():
    src = DESKTOP_JS.read_text()
    assert "_applyLiveTitle(w, baseId, data)" in src, "al montar"
    assert "this._applyLiveTitle(ww, ww.base || id, data)" in src, \
        "y al refrescar: una búsqueda nueva cambia el título, y dejar el viejo es un rótulo que MIENTE"
    assert "if(w._liveTitle) return;" in src, "el nombre del catálogo no puede volver a pisar la tarea"


def test_the_canonical_name_is_not_lost_only_moved():
    """Es como se dirige la pieza por voz: no puede desaparecer, solo dejar de ocupar el sitio principal."""
    src = DESKTOP_JS.read_text()
    fn = src[src.index("async _applyLiveTitle("):src.index("_wireDrag(card, grip)")]
    assert "nameBtn.title" in fn and "alias" in fn


def test_the_title_is_said_once_not_twice():
    """Con la tarea ya en la cabecera de la tarjeta, repetirla dentro en cuerpo mayor era el mismo texto dos veces
    a 4px de diferencia: ruido, y una línea perdida en la parte más valiosa de la hoja."""
    src = WIDGET_JS.read_text()
    assert 'el.dataset.hostTitle !== "1"' in src
    assert 'w.body.dataset.hostTitle = "1"' in DESKTOP_JS.read_text()
    # …pero se conserva el respaldo: si la superficie se monta sin cabecera del canvas, la tarea no desaparece
    assert 'elem("div","hr-hd", data.title || "Resultados")' in src


def test_the_header_does_not_run_under_the_window_buttons():
    """Los botones de la derecha son DOS desde que existe ⤢ (ocupa de 38 a 64): con la cabecera acabando en 40 un
    título largo se le metía por debajo — invisible con un nombre corto y centrado, evidente con una frase."""
    src = DESKTOP_JS.read_text()
    head = src[src.index(".hb-head{"):src.index(".hb-head{") + 200]
    assert "right:70px" in head


def test_the_sticky_header_has_a_bounded_height():
    """Cada línea de la cabecera pegajosa se la quita a los resultados en TODO el scroll. El subtítulo real llegaba
    a tres líneas: se acota a dos EN PANTALLA y el texto íntegro queda en el tooltip — controlar el espacio no es
    lo mismo que recortar el dato."""
    src = WIDGET_JS.read_text()
    assert "-webkit-line-clamp:2" in src
    assert 'elem("div","hr-sub clamp2", data.subtitle)' in src
    assert "sub.title = data.subtitle" in src, "el texto completo no se pierde: va al tooltip"
