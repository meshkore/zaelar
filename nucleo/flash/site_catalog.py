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

This catalog is deliberately part of the ENGINE's own code (not config, not a per-deployment override) — the
operator's explicit requirement (2026-08-17) is that a self-hosted install and a cloud install resolve to the
SAME known-good sites by default, the same way `router_guards._KNOWN_SITES` already does for login/auth intent.
It is consulted by giving the worker the catalog as a DIRECTIVE in its own prompt, not by classifying the task
into a category in code — the worker (a real reasoning model with tools) decides which entry, if any, applies,
consistent with this codebase's standing rule against hardcoded intent classification
([[feedback_no_hardcoded_understand]]): recover candidates, let the model decide.

A named, specific business is NOT an exception to this catalog — it is the common case an aggregator already
covers. Only when the aggregator genuinely doesn't list it should the worker fall back to the business's own
site, per `directive_block()`'s wording.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SiteEntry:
    name: str
    url: str
    note: str  # short usage guidance for the worker, in the same language as _web_prompt's own instructions


SITE_CATALOG: dict[str, SiteEntry] = {
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
        "productos nuevos genéricos (electrónica, libros, etc.) donde no aplica ningún clasificado — ordena "
        "por relevancia/valoración, no solo por precio."),
}


def directive_block() -> str:
    """Render the catalog as a short directive block for the worker's own system prompt (`_web_prompt`).
    Spanish, matching the rest of that prompt's language — this is runtime product text sent to the worker
    model, not developer documentation."""
    lines = [
        "SITIOS DE CONFIANZA POR CATEGORÍA (úsalos SIEMPRE primero, incluso si el operador ha nombrado un "
        "negocio concreto — búscalo DENTRO del sitio de confianza antes de ir a su web propia; solo salta "
        "directo a la web propia de un negocio si genuinamente no aparece listado en el sitio de confianza "
        "de su categoría):"
    ]
    for entry in SITE_CATALOG.values():
        lines.append(f"• {entry.name} ({entry.url}) — {entry.note}")
    return "\n".join(lines)
