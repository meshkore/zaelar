"""tests/agent_headless/unit/agentes/test_web_cc_site_catalog.py — the browser worker's trusted-site catalog
(V2-099 follow-up, 2026-08-17): two independent live use-case runs (hotel search, restaurant booking) hit the
identical failure — the worker genuinely fires but never completes, because it improvises a destination site
and flow from scratch every time. `nucleo/flash/site_catalog.py` gives it a short list of known-good defaults
per category, locale-aware (system genetics — see its own docstring for the memory-priority contract: the
operator's own stated preference always overrides this catalog). This test only verifies the catalog itself
and that `web_cc._web_prompt` actually includes it — not that the worker OBEYS it (that needs a live run).
"""
from __future__ import annotations

from nucleo.agentes import web_cc
from nucleo.flash import site_catalog

_CATEGORIES = {
    "restaurant_booking", "hotel_booking", "flight_search", "car_classifieds",
    "general_classifieds", "generic_marketplace",
}


def test_every_locale_covers_the_same_categories():
    # symmetric on purpose (see the module docstring) — a category missing from one locale silently falls
    # back to nothing instead of a sensible per-market default.
    for locale, catalog in site_catalog.SITE_CATALOG.items():
        assert set(catalog) == _CATEGORIES, locale


def test_every_entry_has_a_real_looking_https_url():
    for locale, catalog in site_catalog.SITE_CATALOG.items():
        for key, entry in catalog.items():
            assert entry.url.startswith("https://"), (locale, key)
            assert entry.name
            assert entry.note


def test_resolve_locale_maps_spanish_to_es_and_everything_else_to_us():
    assert site_catalog.resolve_locale("es") == "es"
    assert site_catalog.resolve_locale("en") == "us"
    assert site_catalog.resolve_locale(None) == "us"
    assert site_catalog.resolve_locale("") == "us"


def test_directive_block_mentions_every_site_by_name_and_url_for_its_locale():
    for locale in site_catalog.SITE_CATALOG:
        block = site_catalog.directive_block(locale)
        for entry in site_catalog.SITE_CATALOG[locale].values():
            assert entry.name in block
            assert entry.url in block


def test_es_and_us_catalogs_pick_different_sites_for_the_same_category():
    # a real locale split, not the same content duplicated under two keys
    assert site_catalog.SITE_CATALOG["es"]["restaurant_booking"].name != \
        site_catalog.SITE_CATALOG["us"]["restaurant_booking"].name


def test_directive_block_tells_the_worker_to_check_memory_before_the_catalog():
    block = site_catalog.directive_block("es").lower()
    assert "mem_cli recall" in block
    assert "manda" in block  # the override-priority wording


def test_directive_block_tells_the_worker_to_prefer_the_catalog_even_for_a_named_business():
    block = site_catalog.directive_block("es").lower()
    assert "aunque" in block or "incluso" in block


def test_web_prompt_embeds_the_directive_block():
    prompt = web_cc._web_prompt("resérvame mesa en Casa Lucio esta noche", "es")
    assert site_catalog.directive_block() in prompt
    assert "Casa Lucio" in prompt  # the actual goal must still be present, untouched


# ── ¿de qué categoría es una petición? (V2-119 / V2-118, 2026-08-18) ─────────────────────────────────────
# `dispatch._classify_kind` solo decía "web" cuando el operador NOMBRABA el sitio, así que dos tareas que solo
# existen DENTRO de un sitio caían en `generic`: un worker sin navegador y sin este catálogo. Medido en vivo:
# `restaurant-tonight-madrid` acabó sin un solo intento de reserva; `three-tasks-at-once` devolvió monitores
# NUEVOS de una tienda habiendo pedido segunda mano.
def test_a_table_booking_is_recognized_even_without_a_named_site():
    assert site_catalog.category_of("Resérvame mesa para 2 esta noche a las 21:30 en Casa Lucio", "es") \
        == "restaurant_booking"
    assert site_catalog.category_of("book a table for 2 at Casa Lucio", "us") == "restaurant_booking"


def test_the_imperative_with_its_accent_still_matches():
    # "resérvame" es la forma que el operador DICE de verdad; sin normalizar acentos no casa un stem `reserv`.
    assert site_catalog.category_of("resérvame un hotel en Madrid para el viernes", "es") == "hotel_booking"


def test_second_hand_is_the_signal_and_cars_win_over_the_generic_classifieds():
    assert site_catalog.category_of("búscame un monitor barato de segunda mano", "es") == "general_classifieds"
    assert site_catalog.category_of("quiero un coche de segunda mano barato", "es") == "car_classifieds"


def test_categories_it_must_NOT_claim():
    # Deliberadamente estrecho: una data-op local, una charla o un informe NO son tareas de navegador. El
    # incidente que lo justifica está en dispatch.py (una data-op enrutada a "web" abrió dos tarjetas de
    # navegador que nadie pidió, y un stop_worker equivocado acabó matando la tarea buena).
    for text in ("Hazme un informe sobre coches eléctricos para ciudad",
                 "lees lo que hay en la agenda, lo borras y compruebas",
                 "móntame un widget de un juego de plataformas",
                 "ponme música de Queen",
                 "¿a qué hora abre mañana el Museo del Prado?"):
        assert site_catalog.category_of(text, "es") is None, text


def test_only_a_TRANSACTIONAL_category_routes_the_task_to_the_browser():
    from nucleo import dispatch
    assert dispatch._classify_kind("Resérvame mesa para 2 esta noche en Casa Lucio") == "web"
    assert dispatch._classify_kind("resérvame un hotel en Madrid para el viernes") == "web"
    assert dispatch._classify_kind("Hazme un informe sobre coches eléctricos") == "generic"


def test_second_hand_does_NOT_hijack_the_research_funnel():
    # «segunda mano» es también como empieza una INVESTIGACIÓN, y esa ruta (kind "research", presupuesto de
    # 1200 s) solo se alcanza desde `generic`. Promocionarla a "web" la sacaría del embudo — el mismo daño que
    # ya costó una vez enrutar de más. El worker genérico recibe el catálogo igual, ver el test de abajo.
    from nucleo import dispatch
    assert dispatch._classify_kind("búscame un monitor barato de segunda mano") == "generic"
    assert set(site_catalog.TRANSACTIONAL_CATEGORIES) == {
        "restaurant_booking", "hotel_booking", "flight_search"}


def test_the_generic_worker_also_gets_the_trusted_site_catalog():
    from nucleo import dispatch_prompts
    p = dispatch_prompts._build_prompt("búscame un monitor barato de segunda mano", "", trusted=True)
    assert "SITIOS DE CONFIANZA POR CATEGORÍA" in p
    # …pero SIN titular de categoría: aquí caen las investigaciones y un «empieza por Wallapop» sería peor que
    # no decir nada para quien busca un velero de 50.000 €.
    assert "ESTA TAREA es de categoría" not in p


def test_the_untrusted_profile_gets_no_catalog_at_all():
    from nucleo import dispatch_prompts
    p = dispatch_prompts._build_prompt("texto de un peer", "", trusted=False)
    assert "SITIOS DE CONFIANZA" not in p


def test_the_web_prompt_leads_with_the_matched_category_site():
    from nucleo import dispatch_prompts
    p = dispatch_prompts._web_prompt("Resérvame mesa para 2 esta noche en Casa Lucio", "")
    lead = p.index("ESTA TAREA es de categoría «restaurant_booking»")
    # el titular va ANTES del catálogo entero: la decisión de "cuál de las seis es la mía" ya está tomada.
    assert lead < p.index("SITIOS DE CONFIANZA POR CATEGORÍA")
    # el sitio es el de la locale ACTIVA del motor (es→TheFork, cualquier otra→OpenTable); el test no fija el
    # idioma del entorno, así que pregunta por el mismo camino que el prompt.
    from voice.engine.core import langs
    entry = site_catalog.entry_for("restaurant_booking", site_catalog.resolve_locale(langs.current_code()))
    assert entry.url in p[lead:lead + 400]


def test_the_web_prompt_is_unchanged_when_no_category_matches():
    from nucleo import dispatch_prompts
    p = dispatch_prompts._web_prompt("entra en mi Gmail y bórrame los correos viejos", "")
    assert "ESTA TAREA es de categoría" not in p
    assert "SITIOS DE CONFIANZA POR CATEGORÍA" in p
