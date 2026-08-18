"""nucleo/flash/site_catalog.py — default "trusted/tested" site per task category for the browser worker.

Why this exists: without it, the web worker picks a destination site from its own model knowledge on every
single task, improvising a brand-new booking/search flow each time — including learning an arbitrary
individual business's own web infrastructure from scratch. Two independent live use-case runs (V2-099,
`tests/use_cases/`) hit the identical failure shape from this: the worker genuinely spawns and navigates, but
never completes within a normal conversation's patience budget, because it is re-deriving how a never-seen
site works instead of using a flow it already knows.

Consulted from **`nucleo/dispatch_prompts.py::_web_prompt()`** — the actual live prompt-builder for a web/
navegador task, called from `nucleo/dispatch.py` and fed uniformly to whichever Brain Worker backend is
configured (`claude_code`/`codex`/`grok_build` — `nucleo/workers/registry.py::get_backend`), so this catalog
applies the same way regardless of backend or deployment. `nucleo/agentes/web_cc.py::_web_prompt()` also
carries it, for consistency, but that module is PARKED (superseded by V2-038's interactive worker sessions;
see CLAUDE.md's Brain Workers decision) and not on the live path today.

## System genetics vs. operator memory — the priority contract (operator, 2026-08-17)

This file is a SYSTEM-level, INITIAL reference — it ships with the engine, versioned in the repo, and is
meant to grow over time (more locales, more categories, economic/pricing preferences) edited by developers
or the system itself, same status as the rest of the "genetic" defaults in `nucleo/` (BRAIN RULES,
`router_guards._KNOWN_SITES`, etc.). It is deliberately generic — a reasonable default for someone who has
never told zaelar otherwise.

**The operator's own memory always wins over this file.** If the operator has ever said something like "usa
siempre Idealista para pisos" or "prefiero PcComponentes a Amazon", that preference is a real, durable memory
pill (written the normal way, by the standard conversational ingest — nothing here writes to memory) and
MUST override the catalog entry below for that category. `directive_block()`'s own text tells the worker to
check memory FIRST via `mem_cli recall` before falling back to this catalog — so the override lives entirely
in the PROMPT, not in a second data source that could drift out of sync with this one. This file never
becomes stale by an operator's personal taste; it only goes stale if a whole category's best-known site
changes for everyone (in which case a dev edits it here, same as any other genetic default).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SiteEntry:
    name: str
    url: str
    note: str  # short usage guidance for the worker, in the same language as _web_prompt's own instructions


# locale → category → SiteEntry. Locale matches the same "es"/"us" split already used throughout
# tests/use_cases/ — not a full country catalog yet (that's exactly the growth the operator described:
# more locales/countries/languages over time, each its own top-level key here, never a rewrite of this
# module's shape). Add a new locale by adding a new top-level dict; add a new category by adding a key to
# EVERY existing locale (kept symmetric on purpose — a category missing from one locale would silently fall
# back to nothing rather than a sensible default for that market).
SITE_CATALOG: dict[str, dict[str, SiteEntry]] = {
    "es": {
        "restaurant_booking": SiteEntry(
            "TheFork / ElTenedor", "https://www.thefork.es",
            "reservar mesa en un restaurante — busca el nombre del restaurante ahí dentro si el operador ha "
            "nombrado uno concreto; si no, filtra por zona/tipo de cocina/hora."),
        "hotel_booking": SiteEntry(
            "Booking.com", "https://www.booking.com",
            "buscar/reservar alojamiento — filtra por ciudad, fechas, nº de personas, estrellas y precio."),
        "flight_search": SiteEntry(
            "Skyscanner", "https://www.skyscanner.es",
            "buscar/comparar vuelos — filtra por origen, destino, fechas y equipaje facturado si se pidió."),
        "car_classifieds": SiteEntry(
            "coches.net", "https://www.coches.net",
            "coches de segunda mano — usa la URL de resultados con filtros (combustible, km, precio máx)."),
        "general_classifieds": SiteEntry(
            "Wallapop", "https://es.wallapop.com",
            "motos/bicis/cámaras/guitarras/objetos varios de segunda mano — filtra por categoría y precio."),
        "generic_marketplace": SiteEntry(
            "Amazon", "https://www.amazon.es",
            "productos nuevos genéricos (electrónica, libros, etc.) donde no aplica ningún clasificado — "
            "ordena por relevancia/valoración, no solo por precio."),
    },
    "us": {
        "restaurant_booking": SiteEntry(
            "OpenTable", "https://www.opentable.com",
            "book a table at a restaurant — search the named restaurant inside it if the operator named one; "
            "otherwise filter by area/cuisine/time."),
        "hotel_booking": SiteEntry(
            "Booking.com", "https://www.booking.com",
            "find/book lodging — filter by city, dates, guest count, star rating and price."),
        "flight_search": SiteEntry(
            "Google Flights", "https://www.google.com/travel/flights",
            "search/compare flights — filter by origin, destination, dates and checked baggage if asked."),
        "car_classifieds": SiteEntry(
            "Cars.com", "https://www.cars.com",
            "used cars — use the filtered results URL (fuel type, mileage, max price)."),
        "general_classifieds": SiteEntry(
            "Facebook Marketplace", "https://www.facebook.com/marketplace",
            "used motorcycles/bikes/cameras/guitars/misc items — filter by category and price."),
        "generic_marketplace": SiteEntry(
            "Amazon", "https://www.amazon.com",
            "generic new products (electronics, books, etc.) where no classifieds site applies — sort by "
            "relevance/rating, not just price."),
    },
}

_DEFAULT_LOCALE = "es"


def resolve_locale(code: str | None) -> str:
    """Map an engine language code (`voice.engine.core.langs.current_code()`, today only "es"/"en") to a
    catalog locale. Deliberately narrow — this is a fallback heuristic (language != country), not a real
    geo-resolution; a future locale (e.g. a country-specific split of "es") should be picked explicitly by
    whoever wires it in, not inferred harder here."""
    return "es" if (code or "").strip().lower() == "es" else "us"


def directive_block(locale: str | None = None) -> str:
    """Render the catalog as a short directive block for the worker's own system prompt (`_web_prompt`).
    `locale` defaults to the engine's own active language (es→"es" catalog, anything else→"us") via
    `resolve_locale`; pass one explicitly to override (tests, or a future per-request locale).

    Leads with the memory-priority contract (see module docstring) before the catalog itself — the worker
    must check for an operator override before defaulting to these sites, every time, not just once."""
    loc = locale if locale in SITE_CATALOG else resolve_locale(locale)
    catalog = SITE_CATALOG.get(loc, SITE_CATALOG[_DEFAULT_LOCALE])
    lines = [
        "SITIOS DE CONFIANZA POR CATEGORÍA. ANTES de usar este catálogo, comprueba si el operador tiene una "
        "preferencia YA GUARDADA para esta categoría (p.ej. «usa siempre Idealista para pisos», «prefiero "
        "PcComponentes a Amazon») con "
        "`python -m nucleo.mem_cli recall \"sitio preferido para <categoría>\"` — SI la hay, esa preferencia "
        "MANDA sobre el catálogo de abajo, sin excepción. Si NO la hay, usa el catálogo (SIEMPRE primero, "
        "incluso si el operador ha nombrado un negocio concreto — búscalo DENTRO del sitio de confianza antes "
        "de ir a su web propia; solo salta directo a la web propia de un negocio si genuinamente no aparece "
        "listado en el sitio de confianza de su categoría):"
    ]
    for entry in catalog.values():
        lines.append(f"• {entry.name} ({entry.url}) — {entry.note}")
    return "\n".join(lines)


# ── ¿de qué categoría es esta petición? ──────────────────────────────────────────────────────────────────
# Why this lives HERE and not in dispatch.py: the categories are this module's taxonomy. A detector kept
# somewhere else would drift the moment a category is added — the whole point of `SITE_CATALOG` being
# symmetric across locales is that categories are declared once.
#
# What it is FOR (V2-119/V2-118, measured 2026-08-18): `dispatch._classify_kind` only ever answered "web"
# when the operator NAMED a site ("en Wallapop", "en Amazon"), so two use cases that plainly need a browser
# were dispatched as `generic` — a worker with no browser and no trusted-site directive:
#   · `restaurant-tonight-madrid`: "resérvame mesa para 2 en Casa Lucio" → generic. No booking was ever
#     attempted; the run ended with the model inventing a restaurant policy instead.
#   · `three-tasks-at-once`: "búscame un monitor barato de segunda mano" → generic. It came back with NEW
#     monitors from a retailer, ignoring "second-hand" — precisely what `general_classifieds` exists to fix.
#
# Deliberately NARROW. It is not a verb table standing in for understanding: each entry requires evidence of
# a real-world TRANSACTION or a SECOND-HAND market, which is exactly the evidence that the browser (and this
# catalog's trusted site) is what the task needs. `generic_marketplace` is intentionally NOT detected — the
# bare verb "compra" would sweep in ordinary chat, and the 2026-08-12 incident (`_MODIFY_CODE_RE`'s comment
# above in dispatch.py) is the standing reminder of what a too-eager route costs: a data-op turned into two
# browser cards nobody asked for. When in doubt this returns None and the old behaviour stands.
import re as _re
import unicodedata as _ud


def _norm(text: str) -> str:
    """Accent-stripped lowercase — the same normalization `router_guards` uses. Without it "resérvame" does
    not match a `reserv` stem, which is not a corner case in Spanish: it is the imperative, i.e. the single
    most common form the operator actually speaks."""
    n = _ud.normalize("NFKD", text or "")
    return "".join(c for c in n if not _ud.combining(c)).lower()


_CAT_PATTERNS: list[tuple[str, "_re.Pattern[str]"]] = [
    # A table booking: the reservation verb plus what is being reserved. Both halves required — "reserva" on
    # its own is also how one talks about a hotel, a flight or a doctor's appointment.
    ("restaurant_booking", _re.compile(
        r"\b(reserv\w*|book|booking)\b[^.!?]{0,60}\b(mesa|table|restaurante?|restaurant|cenar|comer|almorzar)\b"
        r"|\b(mesa|table)\b[^.!?]{0,40}\b(para|for)\s+\d+", _re.I)),
    ("hotel_booking", _re.compile(
        r"\b(reserv\w*|book|booking)\b[^.!?]{0,60}\b(hotel|habitaci[oó]n|alojamiento|hostal|apartamento|room|"
        r"lodging|stay)\b", _re.I)),
    ("flight_search", _re.compile(
        r"\b(vuelos?|flights?|billetes?\s+de\s+avi[oó]n|plane\s+tickets?)\b", _re.I)),
    # Second-hand: the market, not the verb. "de segunda mano" / "usado" / "used" is the whole signal — a
    # classifieds site is the only place that answer exists, so a plain web_search cannot serve it.
    ("car_classifieds", _re.compile(
        r"\b(coches?|cars?|furgonetas?|motos?|motorbikes?)\b[^.!?]{0,60}"
        r"\b(segunda\s+mano|de\s+ocasi[oó]n|usados?|usadas?|used|second[\s-]?hand)\b"
        r"|\b(segunda\s+mano|usados?|used|second[\s-]?hand)\b[^.!?]{0,40}\b(coches?|cars?|motos?)\b", _re.I)),
    ("general_classifieds", _re.compile(
        r"\b(segunda\s+mano|de\s+ocasi[oó]n|usado|usada|usados|usadas|used|second[\s-]?hand)\b", _re.I)),
]


# Categorías cuya petición es una ACCIÓN con destino definido: reservar una mesa, una habitación, un vuelo. Son
# las únicas que `dispatch._classify_kind` promociona a "web" por sí solas, y la frontera importa.
#
# Los CLASIFICADOS (segunda mano) quedan FUERA de esa promoción a propósito, aunque este módulo sí los detecte
# para el titular de categoría del prompt: «segunda mano» también es como empieza una INVESTIGACIÓN de verdad
# («busca veleros de segunda mano… entra en la ficha de CADA candidato»), y esa ruta tiene su propio embudo con
# su propio presupuesto (`nucleo/research.py`, kind "research", 1200 s) al que solo se llega desde `generic`.
# Mandar esa petición al navegador la sacaría del embudo — el mismo tipo de daño que ya causó una vez enrutar de
# más (ver el incidente de `_MODIFY_CODE_RE` en dispatch.py). Al worker genérico se le da igualmente este
# catálogo, así que «de segunda mano» sigue llegando a Wallapop sin tocar el enrutado.
TRANSACTIONAL_CATEGORIES = frozenset({"restaurant_booking", "hotel_booking", "flight_search"})


def category_of(request: str, locale: str | None = None) -> str | None:
    """The catalog category this request belongs to, or None if it is not one of them.

    Order matters: the specific categories are tested before `general_classifieds`, whose "second-hand"
    signal would otherwise swallow a used-car search that has its own better site."""
    text = _norm(request).strip()
    if not text:
        return None
    loc = locale if locale in SITE_CATALOG else resolve_locale(locale)
    catalog = SITE_CATALOG.get(loc, SITE_CATALOG[_DEFAULT_LOCALE])
    for category, pattern in _CAT_PATTERNS:
        if category in catalog and pattern.search(text):
            return category
    return None


def entry_for(category: str, locale: str | None = None) -> SiteEntry | None:
    """The trusted site for a category in a locale (None if either is unknown)."""
    loc = locale if locale in SITE_CATALOG else resolve_locale(locale)
    return SITE_CATALOG.get(loc, SITE_CATALOG[_DEFAULT_LOCALE]).get(category)
