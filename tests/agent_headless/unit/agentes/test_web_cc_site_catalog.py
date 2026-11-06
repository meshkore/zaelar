"""tests/agent_headless/unit/agentes/test_web_cc_site_catalog.py — the browser worker's trusted-site catalog
(V2-099 follow-up, 2026-08-17): two independent live use-case runs (hotel search, restaurant booking) hit the
identical failure — the worker genuinely fires but never completes, because it improvises a destination site
and flow from scratch every time. `nucleo/flash/site_catalog.py` gives it a short list of known-good defaults
per category, locale-aware (system genetics — see its own docstring for the memory-priority contract: the
operator's own stated preference always overrides this catalog). This test only verifies the catalog itself
and that the web worker's prompt (`dispatch_prompts._web_prompt`) actually includes it — not that the worker OBEYS it (that needs a live run).
"""
from __future__ import annotations

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
    # Symmetric on purpose (see the module docstring) — a category missing from one locale silently falls
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
    # A real locale split, not the same content duplicated under two keys.
    assert site_catalog.SITE_CATALOG["es"]["restaurant_booking"].name != \
        site_catalog.SITE_CATALOG["us"]["restaurant_booking"].name


def test_directive_block_tells_the_worker_to_check_memory_before_the_catalog():
    block = site_catalog.directive_block("es").lower()
    assert "cli.mem recall" in block
    assert "manda" in block  # the override-priority wording


def test_directive_block_tells_the_worker_to_prefer_the_catalog_even_for_a_named_business():
    block = site_catalog.directive_block("es").lower()
    assert "aunque" in block or "incluso" in block


def test_web_prompt_embeds_the_directive_block():
    # V2-778 F2-23: the parked `web_cc` copy was deleted; the LIVE web worker prompt is `dispatch_prompts`.
    from tests import worker_briefs   # V2-851 F3: the catalogue is a family the worker reads on request
    prompt = worker_briefs.web("resérvame mesa en Casa Lucio esta noche")
    assert "SITIOS DE CONFIANZA POR CATEGORÍA" in prompt
    assert "Casa Lucio" in prompt  # the actual goal must still be present, untouched


# ── what category is a request? (V2-119 / V2-118, 2026-08-18) ───────────────────────────────────────────
# `dispatch._classify_kind` used to say "web" only when the operator NAMED the site, so two tasks that merely
# exist INSIDE a site fell into `generic`: a worker without a browser and without this catalog. Measured live:
# `restaurant-tonight-madrid` ended with not a single booking attempt; `three-tasks-at-once` returned NEW
# monitors from a store when second-hand had been requested.
def test_a_table_booking_is_recognized_even_without_a_named_site():
    assert site_catalog.category_of("Resérvame mesa para 2 esta noche a las 21:30 en Casa Lucio", "es") \
        == "restaurant_booking"
    assert site_catalog.category_of("book a table for 2 at Casa Lucio", "us") == "restaurant_booking"


def test_the_imperative_with_its_accent_still_matches():
    # "resérvame" is the form the operator actually SAYS; without normalizing accents, a `reserv` stem does not match.
    assert site_catalog.category_of("resérvame un hotel en Madrid para el viernes", "es") == "hotel_booking"


def test_second_hand_is_the_signal_and_cars_win_over_the_generic_classifieds():
    assert site_catalog.category_of("búscame un monitor barato de segunda mano", "es") == "general_classifieds"
    assert site_catalog.category_of("quiero un coche de segunda mano barato", "es") == "car_classifieds"


def test_categories_it_must_NOT_claim():
    # Deliberately narrow: a local data op, a chat, or a report are NOT browser tasks. The incident justifying
    # this is in dispatch.py (a data op routed to "web" opened two browser cards nobody requested, and a
    # mistaken stop_worker ended up killing the good task).
    for text in ("Hazme un informe sobre coches eléctricos para ciudad",
                 "lees lo que hay en la agenda, lo borras y compruebas",
                 "móntame un widget de un juego de plataformas",
                 "ponme música de Queen",
                 "¿a qué hora abre mañana el Museo del Prado?"):
        assert site_catalog.category_of(text, "es") is None, text



def test_the_generic_worker_also_gets_the_trusted_site_catalog():
    from tests import worker_briefs
    p = worker_briefs.generic("búscame un monitor barato de segunda mano")
    assert "SITIOS DE CONFIANZA POR CATEGORÍA" in p
    # …but WITHOUT a category heading: research requests land here, and «start with Wallapop» would be worse
    # than saying nothing to someone looking for a €50,000 sailboat.
    assert "ESTA TAREA es de categoría" not in p


def test_the_untrusted_profile_gets_no_catalog_at_all():
    from nucleo.workers import prompts as dispatch_prompts
    p = dispatch_prompts._build_prompt("texto de un peer", "", trusted=False)
    assert "SITIOS DE CONFIANZA" not in p


def test_the_web_prompt_leads_with_the_matched_category_site():
    from nucleo.workers import prompts as dispatch_prompts
    p = dispatch_prompts._web_prompt("Resérvame mesa para 2 esta noche en Casa Lucio", "")
    lead = p.index("ESTA TAREA es de categoría «restaurant_booking»")
    # The heading travels with the goal; the whole catalog is the `sites` family, on request (V2-851 F3).
    assert "SITIOS DE CONFIANZA POR CATEGORÍA" not in p
    # The site is the one for the engine's ACTIVE locale (es→TheFork, anything else→OpenTable); the test does not
    # fix the environment's language, so it asks through the same path as the prompt.
    from voice.engine.core import langs
    entry = site_catalog.entry_for("restaurant_booking", site_catalog.resolve_locale(langs.current_code()))
    assert entry.url in p[lead:lead + 400]


def test_the_web_prompt_is_unchanged_when_no_category_matches():
    from nucleo.workers import prompts as dispatch_prompts
    p = dispatch_prompts._web_prompt("entra en mi Gmail y bórrame los correos viejos", "")
    assert "ESTA TAREA es de categoría" not in p
    from nucleo.workers.prompts import catalog
    assert "SITIOS DE CONFIANZA POR CATEGORÍA" in catalog.full("sites")


# ── a NAMED site the engine already knows (V2-126, 2026-08-18) ───────────────────────────────────────────
# There were TWO unsynchronized inventories of known sites: `dispatch._WEB_RE` (wallapop, amazon, linkedin,
# «open the web»…) and `router_guards._KNOWN_SITES` (fifteen, the ones the engine knows how to open for a login).
# TWELVE existed only in the second. Measured in `cancel-subscription-before-charge`: «Cancel my Netflix
# subscription» → `generic`, meaning a worker WITHOUT a browser — and without a browser the task cannot even
# reach the login wall, so the system is left without the only honest answer it had («I can't access your account»).

def test_a_pure_login_is_still_a_login_not_a_task():
    # WHETHER he asks to sign in is the brief's `login_only` verdict (V2-857 phase 8, 2.1620); the SITE of that login
    # still comes from his words, and a login inside a task is never opened as a bare login.
    from nucleo.flash import web_auth
    for req, site in (("conéctame a Wallapop", "wallapop.com"), ("inicia sesión en mi Netflix", "netflix.com"),
                      ("vincula mi LinkedIn", "linkedin.com")):
        assert web_auth.fallback_site(req) == site, req
