"""What a use case is ABOUT — the grouping above the tier, and below the language.

Operator's ask, 2026-09-16: «no creo que 100 casos de uso sean genéricos […] pero agrupadores
principales. Por ejemplo, encontrar un monitor o encontrar una cámara o encontrar un barco o un coche
de segunda mano. Para mí todo eso forma parte de los tests de hacer estudios o búsquedas complejas».

Three axes, and they answer three different questions — mixing any two of them is how a 166-row list
becomes unreadable:

  · **locale** (es · us) — WHICH SET of cases exists. The primary index; a different market is a
    different product (`tests/platform/families.py`).
  · **theme** (this file) — WHAT THE PERSON IS TRYING TO DO. Twenty `search-buy-*` rows are one
    capability measured twenty times over; a rail that lists them one by one buries the fact that
    «vídeo» has four cases and «documentos» has three.
  · **tier** (1..7) — HOW HARD it is. Already in the catalog, and it stays a tag rather than a
    grouping: the ladder is how coverage GROWS, not how a person reads the board.

## Why an explicit table and not keyword matching

A prefix rule (`search-buy-*` → búsquedas) covers the twenty easy ones and silently mis-files the
interesting ones: `track-price-drop-buy` is a standing task that happens to end in a purchase,
`show-real-photo-of-a-new-car` is a search that never buys anything, `find-theatre-tickets` is a
booking with a known target. A table is longer and it is right, and when a case moves theme somebody
had to decide that it moved.

## An unclassified case is VISIBLE, never hidden

`theme_of` returns `otros` for anything not in the table, and `tests/use_cases/unit/` fails on it. A
case that quietly vanished from the rail because nobody gave it a theme is exactly the failure mode
`unmapped` exists to prevent on the pytest side.
"""
from __future__ import annotations

#: Ordered — this is the order the rail and the case list use. Id, label, and the one-line question
#: the group answers, in the operator's language (this is a surface he reads, not code comments).
THEMES: tuple[dict[str, str], ...] = (
    {"id": "search", "label": "Búsquedas y estudios",
     "hint": "encontrar, comparar y elegir: segunda mano, precios, especificaciones"},
    {"id": "booking", "label": "Reservas y citas",
     "hint": "mesa, hotel, médico, barbero, entradas — con un objetivo concreto"},
    {"id": "travel", "label": "Viajes y desplazamientos",
     "hint": "vuelos, escapadas, rutas, paquetes en camino"},
    {"id": "agenda", "label": "Agenda y recordatorios",
     "hint": "citas que entran enteras, la semana leída de vuelta, avisos"},
    {"id": "messaging", "label": "Mensajería y correo",
     "hint": "leer, buscar dentro, contestar y ordenar la bandeja"},
    {"id": "media", "label": "Vídeo y música",
     "hint": "poner, controlar y curar lo que suena o se ve"},
    {"id": "files", "label": "Documentos y archivos",
     "hint": "un informe encargado llega como documento, no como una parrafada"},
    {"id": "money", "label": "Dinero y trámites",
     "hint": "facturas, suscripciones, seguros, papeleo con fecha límite"},
    {"id": "widgets", "label": "Widgets y pantalla",
     "hint": "construir una pieza, manejarla sin nombrarla, varias cosas a la vez"},
    {"id": "standing", "label": "Encargos permanentes",
     "hint": "nada de esto se cierra en un turno: vigila y actúa cuando toca"},
    {"id": "agents", "label": "Coordinación con otros agentes",
     "hint": "hablar con el agente de otra persona, o por un canal de mensajería"},
    {"id": "otros", "label": "Sin clasificar",
     "hint": "un caso sin tema — es un defecto de catálogo, no una categoría"},
)

THEME_IDS: tuple[str, ...] = tuple(t["id"] for t in THEMES)

#: case id -> theme id. Keyed by the BARE case id, which ES and US share wherever the case is the same
#: task in both markets (`search-buy-camera` exists twice, once per locale, and is one theme).
_BY_ID: dict[str, str] = {}


def _assign(theme: str, *ids: str) -> None:
    for case_id in ids:
        _BY_ID[case_id] = theme


_assign("search",
        # V2-728 — no es una búsqueda nueva: es volver a ABRIR el informe de una que ya se hizo. Vive en
        # «Búsquedas» porque lo que entrega es exactamente eso (la lista, con sus descartados y sus
        # criterios) y porque el fallo que mide es de ese tema: que la vuelva a buscar en vez de recuperarla.
        "flat-hunt-recall-the-report",
        "search-buy-apartment", "search-buy-bicycle", "search-buy-boat-multicountry", "search-buy-book",
        "search-buy-camera", "search-buy-camper", "search-buy-ebike", "search-buy-guitar",
        "search-buy-laptop", "search-buy-motorcycle", "search-buy-phone", "search-buy-ski-gear",
        "search-buy-sneakers", "search-buy-sofa", "search-buy-stroller", "search-buy-surfboard",
        "search-buy-tv", "search-buy-used-car", "search-buy-vinyl", "search-buy-washing-machine",
        "search-buy-watch", "search-secondhand-monitor", "cheapest-monitor", "search-rent-apartment",
        "search-holiday-rental", "used-car-search-wallapop", "house-search-los-angeles",
        "buy-known-product", "show-real-photo-of-a-new-car", "compare-broadband-plans",
        "compare-phone-plans", "compare-insurance-quotes", "found-next-apartment",
        "things-to-do-nearby-weekend", "kid-friendly-activity-nearby", "quick-fact-opening-hours")

_assign("booking",
        "restaurant-tonight-madrid", "restaurant-tonight-nyc", "search-restaurant-occasion",
        "book-barber-slot", "weekend-barber-availability", "book-hotel-night-known",
        "find-best-hotel-city", "hotel-under-15-days", "hotel-many-filters-at-once",
        "best-pediatric-dentists", "best-plumber-same-day", "find-theatre-tickets",
        "find-concert-tickets", "renew-gym-membership", "reorder-prescription",
        "best-rated-rental-car", "rental-car-automatic-airport", "moms-birthday-flowers-onetime")

_assign("travel",
        "compare-flights-madrid-lisboa", "compare-flights-sf-austin", "find-direct-flight-budget",
        "rebook-delayed-flight-now", "weekend-trip-san-sebastian", "weekend-trip-austin",
        "driving-time-with-traffic", "track-package-reschedule")

_assign("agenda",
        "agenda-appointment-lifecycle", "dentist-appointment-into-agenda", "what-does-my-week-look-like",
        "remember-and-remind-deadline", "weekly-appointment-until-june")

_assign("messaging",
        "show-my-messages", "dictate-a-reply-honestly", "messaging-detail-inside-messages",
        "messaging-did-we-reply", "messaging-school-wrote-last-month", "messaging-group-amount-due",
        "messaging-group-open-actions", "clean-and-reply-inbox", "archive-newsletters",
        "connect-email-by-voice")

_assign("media",
        "watch-a-video-not-listen-to-it", "video-search-lands-in-player", "video-blocked-channel-respected",
        "build-a-video-playlist-from-links", "play-music-and-build-playlist", "music-save-what-is-sounding",
        # V2-739 — routing with several cards in front, and a queue handled by imprecise reference.
        "tres-tarjetas-y-el-video-por-alusion", "la-cola-de-video-con-palabras-imprecisas",
        "music-playlist-reads-clean")

_assign("files",
        "docs-single-recipe-not-a-list", "docs-report-lands-as-document", "file-expense-report")

_assign("money",
        "pay-known-bill", "cancel-subscription-before-charge", "negotiate-lower-phone-bill",
        "split-dinner-bill-friends", "renew-passport-before-expiry", "itv-before-deadline",
        "smog-check-before-deadline")

_assign("widgets",
        "build-workout-tracker-widget", "video-exit-fullscreen-unnamed", "three-tasks-at-once")

_assign("standing",
        "cancel-trial-before-it-charges", "grocery-restock-reactive", "gym-membership-no-silent-renew",
        "moms-birthday-flowers-recurring", "track-price-drop-buy", "watch-flight-rebook-automatically",
        "knows-who-i-am-without-being-told-again")

_assign("agents",
        "confirm-restaurant-reservation-together", "confirm-restaurant-together",
        "coordinate-lunch-with-pedro", "coordinate-dinner-with-alex", "plan-joint-trip-with-friend",
        "reschedule-meetup-conflict", "resolve-meetup-conflict", "split-airbnb-with-marta",
        "split-airbnb-with-jordan", "coordinate-lunch-whatsapp", "coordinate-dinner-whatsapp",
        "group-plan-three-friends", "realtime-eta-share", "split-trip-telegram")


def theme_of(case_id: str) -> str:
    """The theme of a case, by its BARE id (no `__es` / `__us` suffix). `otros` when unclassified —
    which is a catalog defect the unit tests fail on, not a resting place."""
    bare = case_id
    for suffix in ("__es", "__us"):
        if bare.endswith(suffix):
            bare = bare[: -len(suffix)]
    return _BY_ID.get(bare, "otros")


def label_of(theme_id: str) -> str:
    for theme in THEMES:
        if theme["id"] == theme_id:
            return theme["label"]
    return theme_id


def unclassified(case_ids) -> list[str]:
    """The ids with no theme. The ratchet reads this; so can anyone adding a batch of cases."""
    return sorted({cid for cid in case_ids if theme_of(cid) == "otros"})
