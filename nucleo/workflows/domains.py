"""nucleo/workflows/domains.py — WHICH KIND of errand is this, lexically and for free (V2-594).

This is the key of the workflow table, and it is deliberately NOT a new list of verbs.

`site_catalog.category_of()` is already the house's lexical classifier for errands, and it is already the
single source shared by `errand_kind` (which picks the task `kind`) and `flash/router_guards` (which decides
escalation). `router_guards` says why in its own comment: *«this guard not knowing that while the kind
classifier did is exactly how two components deciding the same thing end up disagreeing»*. A third opinion
about what «reservar mesa» means is the bug, not the feature — so this module ASKS that one first and only
adds the domains it does not have.

What it adds are the verticals the MESH speaks and the site catalog does not, because the site catalog maps
errands to trusted WEBSITES and there is no trusted website for «un masaje»: wellness, health, shipping,
housing, mobility, food delivery, home services. Those names are not invented either — they are the Oracle's
own intents (`wellness`, `health`, `transport.taxi`, `housing`…), so both sides of the wire agree on the key.

Cost: one regex sweep over a normalised string. No model, no network, no tokens. That is the whole point —
a table that has to be carried in a prompt to be useful would cost more than the work it saves.
"""
from __future__ import annotations

import re
import unicodedata

# The site catalog's categories, mapped onto the domain names the mesh uses. Same errand, one key.
_FROM_CATALOG = {
    "restaurant_booking": "restaurant",
    "hotel_booking": "hotel",
    "flight_search": "flight",
    "event_tickets": "events",
    "local_business": "local",
    "general_classifieds": "shopping",
}

# Only what the catalog cannot name. Bilingual on purpose: the operator speaks Spanish and the Oracle
# classifies better in English, and a domain that only fires in one language is a cache that misses half the
# time — measured on the mesh, where «entradas de concierto» and «concert tickets» resolved differently.
_EXTRA: list[tuple[str, re.Pattern]] = [
    ("wellness", re.compile(r"\b(masaje|masajes|spa|sauna|balneario|bienestar|quiromasaj\w*|"
                            r"massage|wellness|day spa)\b", re.I)),
    ("health",   re.compile(r"\b(m[eé]dico|medica|doctor\w*|dentista|cita m[eé]dica|consulta m[eé]dica|"
                            r"fisioterapeuta|pediatra|vacuna\w*|receta m[eé]dica|"
                            r"doctor|dentist|physio|appointment with a doctor|prescription)\b", re.I)),
    ("train",    re.compile(r"\b(tren|trenes|renfe|ave\b|billete de tren|cercan[ií]as|"
                            r"train|rail|railway)\b", re.I)),
    ("taxi",     re.compile(r"\b(taxi|taxis|vtc|uber|cabify|bolt\b|free ?now|"
                            r"ride|rideshare)\b", re.I)),
    ("car_rental", re.compile(r"\b(alquil\w+ (?:un )?coche|coche de alquiler|alquiler de coches|"
                              r"rent a car|car rental|hire a car)\b", re.I)),
    ("delivery", re.compile(r"\b(comida a domicilio|pedir comida|domicilio|reparto|delivery|"
                            r"takeaway|order food|food delivery)\b", re.I)),
    ("shipping", re.compile(r"\b(paquete|paqueter[ií]a|env[ií]o|env[ií]os|seguimiento del pedido|"
                            r"etiqueta de env[ií]o|correos|parcel|shipment|tracking number|"
                            r"shipping label)\b", re.I)),
    ("housing",  re.compile(r"\b(piso|pisos|alquilar (?:un )?piso|piso en alquiler|vivienda|inmueble|"
                            r"apartamento|idealista|flat to rent|apartment to rent|real estate)\b", re.I)),
    ("home_services", re.compile(r"\b(fontaner\w*|electricista|cerrajer\w*|manitas|reforma|"
                                 r"plumber|electrician|locksmith|handyman)\b", re.I)),
    # The catalog's own categories AGAIN, as a wider fallback — and this is safe here in a way that widening
    # `category_of` itself is NOT. That detector demands a booking VERB for hotels on purpose (V2-477: «busca
    # vuelos» enters and «busca hoteles» does not, because promoting it would pull the `hotel-under-15-days`
    # errand out of the research funnel and its own budget). That reasoning is about ROUTING — which worker
    # gets the task. This table never routes: it only answers «is there a faster channel for this kind of
    # thing?», and answering it for a bare «hotel en Soria» costs nothing and skips a browser. So the strict
    # rule keeps owning `kind`, and the loose one is allowed to own the cache key.
    ("hotel",    re.compile(r"\b(hotel|hoteles|alojamiento|hostal|apartahotel|"
                            r"lodging|accommodation|place to stay)\b", re.I)),
    ("restaurant", re.compile(r"\b(restaurante|restaurantes|cenar|comer fuera|mesa para|"
                              r"restaurant|dinner|somewhere to eat)\b", re.I)),
    ("flight",   re.compile(r"\b(vuelo|vuelos|volar|billete de avi[oó]n|flight|flights|fly to)\b", re.I)),
    ("events",   re.compile(r"\b(entradas|concierto|conciertos|espect[aá]culo|festival|"
                            r"tickets|concert|gig|show)\b", re.I)),
    ("shopping", re.compile(r"\b(comprar|compra online|de segunda mano|ebay|wallapop|"
                            r"buy a|second.hand|listing)\b", re.I)),
    ("image",    re.compile(r"\b(genera\w* (?:una )?imagen|crea\w* (?:una )?imagen|il[uú]stra\w*|"
                            r"generate an image|draw me|create an image|text.to.image)\b", re.I)),
]


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def domain_of(request: str, locale: str | None = None) -> str:
    """The errand domain, or "" when this is not one of them.

    Order matters and is the opposite of a preference: the SITE CATALOG is asked first because it is the
    established classifier and other components already route on it. Only when it says nothing do the extra
    verticals get a turn.
    """
    text = (request or "").strip()
    if not text:
        return ""
    try:
        from nucleo.flash import site_catalog as _sc
        cat = _sc.category_of(text, locale)
        if cat and cat in _FROM_CATALOG:
            return _FROM_CATALOG[cat]
    except Exception:
        pass                                     # the catalog is an optimisation here, never a dependency
    plain = _norm(text)
    for domain, pattern in _EXTRA:
        if pattern.search(plain) or pattern.search(text):
            return domain
    return ""
