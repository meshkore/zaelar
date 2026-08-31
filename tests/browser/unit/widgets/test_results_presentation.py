"""Contract for the GENERIC PRESENTATION SURFACE (`widgets/results`).

Reproduces the use case that failed completely on 2026-08-02 ("search for lively pools near Tarragona and put a
report with photos on screen"): the operator never saw a result. Three chained failures, one per block:

  1. `view_data()` returned a hardcoded DEMO list of the operator's projects (Pricewaterhouse/Mage Core/…) →
     opening the widget for a pool search displayed "Projects". A blank sheet has no content of its own.
  2. There was no way to FILL IT: the only documented channel was the `[[push:results]]` tag, which the voice
     provider blocks and turns into an escalation, and the widget declared only the `choose` action → a Brain Worker
     holding the data had no way to deliver it, so it merely recited it by voice.
  3. Pushed content was ephemeral: any re-render called `view_data()` again and erased the obtained content.

The test is intentionally TOPIC-AGNOSTIC (pools, cars, open-source stories): the widget never knows what the items
are about. It follows the SAME path used by a worker (`brain_action` → `apply_action`), with no shortcuts.
"""
import asyncio

import pytest

from widgets import actions, runtime, store
from widgets.results import data as results


@pytest.fixture(autouse=True)
def _isolated_sheet(tmp_path, monkeypatch):
    """ISOLATED store. The first version of these tests cleared the REAL store between cases and erased the report
    the operator had on screen in the middle of a regression — exactly the failure we are fixing."""
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    store._last_hash.pop("results", None)          # the "identical content" gate is per process, not per directory
    yield
    store._last_hash.pop("results", None)


def _present(**payload):
    """Delivers through the SAME choke point as the worker bridge (`hbwidget data results present …`)."""
    from widgets.server_api import brain_action
    return asyncio.run(brain_action("results", "present", payload))


# ── 1) blank sheet: with nothing delivered, NO content is invented ────────────────────────────────────────
def test_empty_sheet_has_no_content_of_its_own():
    d = results.view_data()
    assert d["items"] == []
    assert d.get("note")                       # says "no results", does not display data from another topic
    blob = repr(d).lower()
    for leak in ("pricewaterhouse", "mage core", "meshkore", "cryptoknight"):
        assert leak not in blob, "the presentation surface must not contain its own demo data"


# ── 2) the result set enters through a DECLARED ACTION, not by rewriting the widget ───────────────
def test_present_is_a_declared_fast_action():
    man = runtime.get("results")
    assert man, "the results widget must exist in the catalog"
    declared = man.get("actions") or {}
    for name in ("present", "append", "clear", "choose"):
        assert name in declared, f"«{name}» must be DECLARED for the worker bridge to accept it"
        # FAST = applied immediately. If it fell into CONFIRM, showing a report would require approval and recreate the failure.
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
    assert top["image"] and top["url"] and top["price"] and top["primary"] is True   # REAL photo+link+price


def test_any_domain_fits_the_same_surface():
    """Nothing in the widget knows the topic: the same contract works for cars or open-source stories."""
    for title, item in (
        ("Coches de segunda mano en Bilbao", {"title": "Golf GTI 2019", "price": "18.500€"}),
        ("Cuentos infantiles open-source", {"title": "The Wandering Fox", "url": "https://example.com/fox"}),
    ):
        assert _present(title=title, items=[item]).get("ok")
        d = results.view_data()
        assert d["title"] == title and d["items"][0]["title"] == item["title"]


# ── 3) delivered content PERSISTS and can be filled progressively ───────────────────────────────────────────────
def test_delivered_results_survive_a_re_render():
    _present(title="Informe", items=[{"title": "Uno"}, {"title": "Dos"}])
    # the canvas repaints by calling view_data() AGAIN: obtained content must not disappear between repaints
    assert [i["title"] for i in results.view_data()["items"]] == ["Uno", "Dos"]
    assert [i["title"] for i in results.view_data()["items"]] == ["Uno", "Dos"]


def test_append_fills_progressively_and_dedups():
    _present(title="Informe", items=[{"title": "Uno", "url": "https://a"}])
    results.apply_action("append", {"items": [{"title": "Uno", "url": "https://a"},      # same finding
                                              {"title": "Dos", "url": "https://b"}]})
    assert [i["title"] for i in results.view_data()["items"]] == ["Uno", "Dos"]
    assert results.apply_action("append", {"items": []})["ok"] is False


def test_choose_persists_the_operators_pick():
    _present(title="Informe", items=[{"title": "Uno"}, {"title": "Dos"}], choosable=True)
    assert results.apply_action("choose", {"title": "Dos"})["ok"]
    assert results.view_data()["chosen"] == "Dos"          # survives the re-render, like the list


# ── 4) the payload comes from the open web → CLOSED schema ───────────────────────────────────────────────
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


# ── 5) "show me a photo/image of X" — one item with ONLY `image`, without url/price (2026-08-03) ─────────
# The actual failure: when asked for a photo, the brain narrated a description instead of showing it because nothing told it that
# THIS is what needs to be filled (see the router fix in nucleo/flash/router.py). The widget itself already accepted it.
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


# ── 6) `lines` accommodates a COMPLETE block of text, not just 4 bullets (2026-08-03) ──────────────────────
# The cap of 4 lines was enough for a technical spec but not for "show me the lyrics of a song" (a real song
# has dozens of verses) — another real case the surface could already cover with a more generous limit.
def test_lines_hold_a_full_block_of_text_like_song_lyrics():
    lyrics = [f"Verso {i} de la canción" for i in range(60)]
    _present(title="Letra de una canción", items=[{"title": "Mi canción", "lines": lyrics}])
    assert results.view_data()["items"][0]["lines"] == lyrics


def test_lines_are_still_bounded_not_unlimited():
    huge = [f"línea {i}" for i in range(500)]
    _present(title="Demasiado largo", items=[{"title": "X", "lines": huge}])
    assert len(results.view_data()["items"][0]["lines"]) == results._MAX_LINES


# ── 7) COMPOSITE PROPOSALS: one result made of pieces (2026-08-09) ──────────────────────────────────────
# Operator's case: "we want to go on vacation… hotel + ferry", and the useful answer is not a list of hotels and
# another of ferries, but THREE COMPLETE PROPOSALS comparable with one another. With the previous flat schema this could only be
# written by dissolving it into prose inside `lines`, which is precisely what prevents comparison.
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
    # each piece carries its OWN price: without this the operator cannot see where the total comes from
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
    """A model writes `facts`, and a model emits all three forms. All three must arrive ORDERED and identical."""
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


# ── 8) SECOND PAGE: "show me proposal one in detail" ────────────────────────────────────────────────
def test_detail_and_list_are_declared_fast_actions():
    declared = (runtime.get("results") or {}).get("actions") or {}
    for name in ("detail", "list"):
        assert name in declared, f"«{name}» debe estar DECLARADA para que el cerebro pueda invocarla"
        assert actions.classify(declared[name], name) == actions.FAST


def test_detail_by_ordinal_because_that_is_how_voice_refers_to_it():
    """By VOICE the operator says «proposal number one», not the hotel's commercial name: the ordinal survives
    STT much better than «Insotel Tarida Beach», so the action must accept it."""
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
    """If the detail survived a `present` that no longer includes that item, the sheet would point to a nonexistent
    result — a blank screen without explanation."""
    _present(title="Propuestas", items=[_plan("Plan A")])
    results.apply_action("detail", {"index": 1})
    _present(title="Otra búsqueda", items=[])
    assert results.view_data().get("view") is None


# ── 9) the brain KNOWS what is on screen (prompt_digest) ────────────────────────────────────────────────
# Without this, when asked "does the hotel in proposal 2 have Wi-Fi?" —a fact WRITTEN on the card the operator
# is viewing— the brain had to guess or escalate a new search to retrieve something it already possessed.
def test_digest_carries_the_hard_facts_so_followups_need_no_new_search():
    _present(title="Propuestas", items=[
        _plan("Plan A", facts={"Wifi": "Sí, gratis"}),
        _plan("Plan B", facts={"Wifi": "De pago, 5€/día"}),
    ])
    dig = results.prompt_digest()
    assert "#1" in dig and "#2" in dig, "the ordinal must be present: it is how the operator refers to each one"
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
    """`widgets/brief.py` cannot know about the «results» widget: the digest is collected through the generic hook, so
    any future widget that implements it appears without touching the bridge."""
    from widgets import refs
    _present(title="Propuestas", items=[_plan("Plan A")])
    assert refs.prompt_digest("results").startswith("#1")
    assert refs.prompt_digest("agenda") == "" or isinstance(refs.prompt_digest("agenda"), str)


# ══ 10) THE OTHER THREE TABS (2026-08-12) ═══════════════════════════════════════════════════════════════════
# Operator rule: this surface will be used for MANY complex searches, and a complex search is not just its result
# — it also includes the criteria used, its progress, and where the data comes from. Those three things existed only verbally
# (the agent had to be asked about them), so they could not be checked.
import pathlib

WIDGET_JS = pathlib.Path("widgets/results/widget.js")


def test_the_four_tabs_are_declared_fast_actions():
    declared = (runtime.get("results") or {}).get("actions") or {}
    for name in ("tab", "sources", "progress", "criteria"):
        assert name in declared, f"«{name}» debe estar DECLARADA para que el puente del worker la admita"
        assert actions.classify(declared[name], name) == actions.FAST


def test_the_open_tab_lives_in_the_payload_so_voice_can_drive_it():
    """Like `view`/`focus`: the tab is NOT browser state. If it were, «show me where you got this» could not move the
    screen, and a reload would lose where the operator was looking."""
    _present(title="P", items=[{"title": "Uno"}])
    assert results.apply_action("tab", {"tab": "sources"})["ok"]
    assert results.view_data()["tab"] == "sources"


def test_the_tab_name_survives_coming_from_voice():
    """It arrives through STT and in the operator's language. Normalizing the argument the model has ALREADY chosen plays
    the same role as the ordinal in `detail` — it is not an intent table."""
    for said in ("fuentes", "Fuentes", "webs"):
        assert results.apply_action("tab", {"tab": said})["tab"] == "sources"
    assert results.apply_action("tab", {"tab": "resumen"})["tab"] == "summary"
    assert results.apply_action("tab", {"tab": "criterios"})["tab"] == "criteria"


def test_an_unknown_tab_is_refused_not_guessed():
    r = results.apply_action("tab", {"tab": "chorradas"})
    assert r["ok"] is False and "sources" in r["error"]


def test_leaving_the_results_tab_closes_the_detail_page():
    """If the detail survived a tab change, returning to «Results» would display a case file instead of
    the list the operator expects."""
    _present(title="P", items=[_plan("Plan A")])
    results.apply_action("detail", {"index": 1})
    results.apply_action("tab", {"tab": "sources"})
    d = results.view_data()
    assert d["tab"] == "sources" and "view" not in d


# ── SOURCES: what turns «I found nothing» into an auditable fact ─────────────────────────────────────────
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
    """A source is announced on entry and closed on exit. If each report created a row, the tab would be a
    log instead of the STATE of each site."""
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


# ── SUMMARY: reported and derived data kept separate ────────────────────────────────────────────────────────────
def test_the_summary_never_passes_off_card_count_as_breadth():
    """Only the worker knows «how many it explored». Without a report, the sheet SAYS so instead of showing the
    number of cards as breadth — exactly the complacency the brief exists to prevent."""
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


# ── CRITERIA: the brief as executed, correctable by voice ───────────────────────────────────────────
def test_criteria_hold_the_brief_and_accumulate_the_operators_corrections():
    results.apply_action("criteria", {"goal": "velero de segunda mano", "hard": ["eslora 40-50 pies"]})
    results.apply_action("criteria", {"changes": ["que sean de 42 a 49 pies"]})
    results.apply_action("criteria", {"changes": ["y con motor diésel"]})
    c = results.view_data()["criteria"]
    assert c["goal"] == "velero de segunda mano" and c["hard"] == ["eslora 40-50 pies"]
    assert c["changes"] == ["que sean de 42 a 49 pies", "y con motor diésel"]


def test_a_correction_does_not_wipe_the_work_in_progress():
    """Correcting a criterion halfway through must NOT discard what was already found: the operator is refining, not
    starting something else."""
    results.apply_action("criteria", {"goal": "velero de segunda mano"})
    _present(title="Veleros", items=[{"title": "Bavaria 46"}])
    results.apply_action("sources", {"sources": [{"name": "Yachtworld", "status": "ok"}]})
    results.apply_action("criteria", {"changes": ["de 42 a 49 pies"]})
    d = results.view_data()
    assert [i["title"] for i in d["items"]] == ["Bavaria 46"] and len(d["sources"]) == 1


def test_a_different_goal_is_a_different_investigation_and_clears_the_stale_sheet():
    """The operator has already experienced being left looking at the results of the PREVIOUS search, believing they were
    theirs. The goal is the brief's signature: if it changes, the sheet is emptied."""
    results.apply_action("criteria", {"goal": "velero de segunda mano"})
    _present(title="Veleros", items=[{"title": "Bavaria 46"}])
    results.apply_action("sources", {"sources": [{"name": "Yachtworld", "status": "ok"}]})
    results.apply_action("progress", {"explored": 40})
    assert results.apply_action("criteria", {"goal": "pisos en Tarragona"})["reset"] is True
    d = results.view_data()
    assert d["items"] == [] and d["sources"] == [] and d["summary"] == {}
    assert d["criteria"]["goal"] == "pisos en Tarragona"


def test_the_goal_becomes_a_headline_not_a_paragraph():
    """Seen live on 2026-08-12: the brief's `goal` is a self-contained paragraph («…and report the status of
    each consulted source»). Used raw as a title, it occupied five lines before showing a single result.
    The full text remains complete in the CRITERIA tab, where it belongs."""
    goal = ("Encontrar los mejores veleros de segunda mano a la venta ahora mismo que cumplan: precio ≤ 50.000 €, "
            "eslora ≤ 20 m, listos para navegar, con amarre en Mediterráneo y motor en buen estado")
    results.apply_action("criteria", {"goal": "algo anterior"})
    results.apply_action("criteria", {"goal": goal})
    d = results.view_data()
    from widgets import presentation
    assert len(d["title"]) <= presentation.contract("results")["sheet_title"] + 1
    assert d["criteria"]["goal"] == goal, "recortar el TÍTULO no puede recortar el criterio"


def test_a_second_round_keeps_the_same_goal_so_it_never_clears():
    """«I'm not convinced, keep searching» increases breadth for the SAME goal (research.expand). If that
    cleared the sheet, continuing a search would erase what had already been found."""
    results.apply_action("criteria", {"goal": "velero de segunda mano"})
    _present(title="Veleros", items=[{"title": "Bavaria 46"}])
    r = results.apply_action("criteria", {"goal": "velero de segunda mano", "min_candidates": 60})
    assert r["reset"] is False
    assert results.view_data()["items"], "una ronda 2 no puede vaciar la hoja"


def test_present_preserves_the_other_three_tabs():
    """A long task makes several `present` calls (provisional → final). Clearing the already reported sources and
    summary on each call would lose data that took minutes of browsing."""
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


# ── the brain SEES all three tabs, so it answers without searching again ─────────────────────────────────────
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
    """The first two minutes case: there is not yet a single result, but the brain can already say what
    is being searched for instead of saying it knows nothing."""
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


# ══ 11) DYNAMIC CARD: each result type is shown differently, WITHOUT accepting HTML ════════════════════════════
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
    """The payload comes from the open web. An unknown `kind` is DISCARDED entirely — it is not degraded to text,
    which would smuggle third-party content through another door."""
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


# ── RATING: it had been in the schema for months and was not rendered anywhere ──────────────────────
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
    """Render contract (frontend tests are string-based): the operator asked for the case file to include
    «the rating and all card data»."""
    src = WIDGET_JS.read_text()
    assert "function scoreBlock(" in src
    assert "scoreBlock(it.score)" in src, "la valoración tiene que salir en el DETALLE, no solo en la tarjeta"
    assert "renderBlocks(it.blocks)" in src, "la ficha a medida también se despliega en el detalle"


# ══ 12) it is a BUILT-IN surface, not a user-created widget ════════════════════════════════════════
def test_the_sheet_ships_with_the_product():
    """It was in the curated `_BUILTINS` list while its manifest declared `origin:"user"` — and the explicit
    manda, así que Config la listaba como «tuyo». Es la superficie con la que zaelar entrega CUALQUIER búsqueda:
    de serie. (Sigue siendo un widget full-stack a propósito: es su `data.py` + acciones declaradas lo que permite
    que un Brain Worker la rellene; una superficie nativa del frontend no tendría por dónde recibir los datos.)"""
    from widgets import registry
    man = runtime.get("results") or {}
    assert registry.origin_of(man) == "builtin"
    assert "results" in registry._BUILTINS


# ══ 13) the DIGEST fits in the prompt without consuming the results ══════════════════════════════════════════════════
def test_the_head_never_squeezes_the_results_out_of_the_digest():
    """The header (summary+sources+criteria) comes FIRST, so without its own cap, long criteria
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
    """Order by IRREPLACEABILITY: only this screen knows a source's status; the criteria were spoken
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


# ══ 14) THE VIEW: the list is SCANNED, the case file is READ (2026-08-12, seen on screen) ═══════════════════════
# With cards rendering all their blocks, ONE card filled the entire sheet — and since the default delivery is ten
# results, that makes the list impossible to scan. Render contracts (frontend tests are string-based): the list gets
# the LIGHT blocks; the heavy ones are what you look for when opening a card.
def test_the_list_shows_a_summary_card_not_the_whole_dossier():
    src = WIDGET_JS.read_text()
    assert "renderBlocks(blocks, {compact: true})" in src, "la LISTA pinta la ficha en modo compacto"
    assert "renderBlocks(it.blocks)" in src, "y el EXPEDIENTE, entera"
    assert "const LIGHT_BLOCKS = new Set([\"chips\"])" in src
    assert 'b.kind === "text" && b.tone === "warn"' in src, \
        "un AVISO no puede quedarse escondido detrás de un clic (regla de presentación)"


def test_the_badge_travels_with_the_title_not_with_the_button():
    """«Best overall» QUALIFIES the result. At the bottom it ended up beside «View details» and read like another button."""
    src = WIDGET_JS.read_text()
    assert "hr-metarow" in src
    i_meta, i_more = src.index("hr-metarow"), src.index('elem("button","hr-more"')
    assert i_meta < i_more


def test_the_numbers_that_get_compared_are_tabular():
    """Composition detail, not whim: on a surface whose job is to place prices and notes one below another,
    otros, dígitos de anchura distinta obligan a releer para saber cuál es mayor."""
    src = WIDGET_JS.read_text()
    i = src.index("font-variant-numeric:tabular-nums")
    block = src[max(0, i - 400):i]
    for cls in ("hr-price", "hr-score", "hr-stat b", "hr-sn", "hr-tbl td"):
        assert cls in block, f"{cls} lleva cifras que se comparan: van tabulares"


def test_the_type_scale_and_spacing_are_a_system_not_ad_hoc_numbers():
    """The previous version accumulated thirteen font sizes and individually chosen margins. That does not read as a
    superficie, se lee como parches. Un techo de magnitudes crudas obliga a usar la escala."""
    src = WIDGET_JS.read_text()
    css = src[src.index("s.textContent=`"):src.index("`; document.head.appendChild(s)")]
    for token in ("--f-body", "--f-micro", "--s3", "--r-md", "--line:"):
        assert token in css, f"falta el token {token} de la escala"
    import re
    # Raw magnitudes IN USE, excluding the token definitions themselves (px are mandatory there) and
    # values below 4px (hairlines, optical half-tones: no scale covers them without looking worse).
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


# ══ 15) THE HEADER STATES THE TASK, NOT THE PIECE NAME (2026-08-12) ════════════════════════════════════════
# Literal operator rule: «people do not need to know that it is the viewer or that it is the results display,
# but rather that it is what we asked for placed there». On a GENERIC surface the catalog name
# («Resultados») no identifica nada — lo que identifica esa tarjeta es el ENCARGO que está mostrando.
DESKTOP_JS = pathlib.Path("frontend/app/widgets/desktop.js")


def test_the_sheet_opts_into_a_live_title():
    """Opt-in PER WIDGET, not global: the clock or agenda are identified by name, and changing it for all
    would be a regression."""
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
    """This is how the piece is addressed by voice: it cannot disappear, only stop occupying the main position."""
    src = DESKTOP_JS.read_text()
    fn = src[src.index("async _applyLiveTitle("):src.index("_wireDrag(card, grip)")]
    assert "nameBtn.title" in fn and "alias" in fn


def test_the_title_is_said_once_not_twice():
    """With the task already in the card header, repeating it inside in larger text was the same text twice
    a 4px de diferencia: ruido, y una línea perdida en la parte más valiosa de la hoja."""
    src = WIDGET_JS.read_text()
    assert 'el.dataset.hostTitle !== "1"' in src
    assert 'w.body.dataset.hostTitle = "1"' in DESKTOP_JS.read_text()
    # …pero se conserva el respaldo: si la superficie se monta sin cabecera del canvas, la tarea no desaparece
    assert 'elem("div","hr-hd", data.title || "Resultados")' in src


def test_the_header_does_not_run_under_the_window_buttons():
    """There have been TWO buttons on the right since ⤢ was added (it occupies 38 to 64): with the header ending at 40, a
    título largo se le metía por debajo — invisible con un nombre corto y centrado, evidente con una frase."""
    src = DESKTOP_JS.read_text()
    head = src[src.index(".hb-head{"):src.index(".hb-head{") + 200]
    assert "right:70px" in head


def test_the_sticky_header_has_a_bounded_height():
    """Every line in the sticky header takes space away from the results throughout the ENTIRE scroll. The real subtitle reached
    a tres líneas: se acota a dos EN PANTALLA y el texto íntegro queda en el tooltip — controlar el espacio no es
    lo mismo que recortar el dato."""
    src = WIDGET_JS.read_text()
    assert "-webkit-line-clamp:2" in src
    assert 'elem("div","hr-sub clamp2", data.subtitle)' in src
    assert "sub.title = data.subtitle" in src, "el texto completo no se pierde: va al tooltip"
