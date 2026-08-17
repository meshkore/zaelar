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
