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

# V2-158: this set went stale the day `event_tickets` (V2-132) and `local_business` (V2-144) were added to the
# catalog, and nothing said so — the file has never been listed in `tests/run_testmap.py`, so `tests run all`
# does not execute it and only a raw `pytest` invocation ever saw the failure. Registered there now. The lesson
# is the one this repo already wrote down for NEW test files (V2-112) and it bites the same way for old ones:
# a test that no suite runs is a test that silently stops being true.
_CATEGORIES = {
    "restaurant_booking", "hotel_booking", "flight_search", "car_classifieds",
    "general_classifieds", "generic_marketplace", "event_tickets", "local_business",
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
    # V2-158: `event_tickets` (V2-132) y `local_business` (V2-144) entraron después. Lo que este test protege no
    # es la LISTA sino que «segunda mano» siga fuera de ella — la línea de arriba.
    assert set(site_catalog.TRANSACTIONAL_CATEGORIES) == {
        "restaurant_booking", "hotel_booking", "flight_search", "event_tickets", "local_business"}
    assert "general_classifieds" not in site_catalog.TRANSACTIONAL_CATEGORIES


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


# ── un sitio NOMBRADO que el motor ya conoce (V2-126, 2026-08-18) ────────────────────────────────────────
# Había DOS inventarios de sitios conocidos, desincronizados: `dispatch._WEB_RE` (wallapop, amazon, linkedin,
# «abre la web»…) y `router_guards._KNOWN_SITES` (quince, los que el motor sabe abrir para un login). DOCE
# estaban solo en el segundo. Medido en `cancel-subscription-before-charge`: «Cancela mi suscripción a Netflix»
# → `generic`, o sea un worker SIN navegador — y sin navegador la tarea no puede ni llegar al muro de login,
# así que el sistema se queda sin la única respuesta honesta que tenía («no puedo entrar en tu cuenta»).
def test_a_named_known_site_plus_a_task_verb_goes_to_the_browser():
    from nucleo import dispatch
    for req in ("Cancela mi suscripción a Netflix antes de que me cobren el día 15",
                "date de baja de Netflix",           # LA forma de decirlo, y no llevaba ningún verbo de tarea
                "cancela mi cuenta de eBay",
                "borra mis publicaciones de Instagram"):
        assert dispatch._classify_kind(req) == "web", req


def test_music_and_messaging_never_go_to_the_browser_even_naming_their_site():
    """Esas cuentas se vinculan DENTRO de su widget (OAuth/QR), nunca por el Chromium — sus dos guards existen
    justo para sostener ese invariante."""
    from nucleo import dispatch
    for req in ("ponme música en Spotify", "conéctame a Spotify", "mándale un mensaje a Ana por WhatsApp"):
        assert dispatch._classify_kind(req) != "web", req


def test_naming_no_site_is_still_not_a_browser_task():
    """El verbo suelto NO basta: `looks_like_web_task` es ancho (lee|mira|revis|compr) y su propio docstring
    dice que existe como DISPARADOR, no como clasificador. Enrutar de más ya costó una vez dos tarjetas de
    navegador que nadie pidió."""
    from nucleo import dispatch
    for req in ("lees lo que hay en la agenda, lo borras y compruebas",
                "Hazme un informe sobre coches eléctricos para ciudad",
                "¿qué tal está Netflix últimamente?"):
        assert dispatch._classify_kind(req) != "web", req


def test_but_ending_a_paid_commitment_IS_a_browser_task_now():
    """V2-158 retira «cancela la suscripción del gimnasio» de la lista de arriba: desde V2-148 un encargo que
    TERMINA un compromiso de pago va al navegador A PROPÓSITO (`money_work_needs_a_browser`), y el argumento
    está escrito en esa decisión — sin navegador la tarea no puede ni llegar al muro del login, así que el
    sistema pierde la única respuesta honesta que tenía y el turno rellena el hueco narrando.

    La afirmación llevaba desde entonces contradiciendo el comportamiento buscado sin que nadie se enterara,
    porque este fichero no estaba en `tests/run_testmap.py`."""
    from nucleo import dispatch
    from nucleo.flash import router_guards as rg
    assert rg.money_work_needs_a_browser("cancela la suscripción del gimnasio") is True
    assert dispatch._classify_kind("cancela la suscripción del gimnasio") == "web"


def test_a_pure_login_is_still_a_login_not_a_task():
    from nucleo.flash import router_guards as rg
    for req in ("conéctame a Wallapop", "inicia sesión en mi Gmail", "vincula mi LinkedIn"):
        assert rg.looks_like_login_request(req), req
