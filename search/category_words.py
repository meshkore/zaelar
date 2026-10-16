"""search/category_words.py — the VOCABULARY of «this row is another category of product» (V2-782 T3.3).

Data only, ES + EN, read by `search/category.py`. Every class below was measured on a real results sheet
(search-buy-used-car ES/EN, cheapest-monitor EN, 2026-10-11): a word belongs here only if a row carrying it was
another kind of thing than the one asked. A class never applies when the REQUEST itself uses one of its words —
«busco piezas para mi coche» asks for parts, so parts are its candidates.

Matched over accent-free lowercase text (`category._norm`), except `CASE_SENSITIVE`, which is matched on the raw
title (the model-railway scale «HO» is a word only in capitals).
"""
from __future__ import annotations

import re

#: Classes that apply to ANY listing request: things that are never an instance of a thing you buy whole.
GENERIC: dict[str, re.Pattern] = {
    "a part or spare": re.compile(
        r"\b(recambios?|repuestos?|piezas?|despiece|desguace|spare parts?|replacement parts?|parts? (?:no|number)|"
        r"placa controladora|controller board|driver board)\b"),
    "a toy or scale model": re.compile(
        r"\b(maquetas?|miniaturas?|juguetes?|toys?|diecast|die-cast|scale models?|model kits?|model trains?|"
        r"locomotor\w*|locomotives?|vagon|vagones|railcars?|1[:/]\d{2,3}|bachmann|marklin|hornby|"
        r"lionel|american flyer|matchbox|hot wheels|maisto|bburago|playmobil|lego)\b"),
    "a guide, catalogue or collectible": re.compile(
        r"\b(guias? (?:oficial )?de precios|price guides?|used car guide|buyer'?s guide|catalogos?|catalog(?:ue)?s?|"
        r"matchcovers?|posters?|postales?|postcards?|revistas?|magazines?|folletos?|brochures?|"
        r"manual de taller|workshop manual|owner'?s manual)\b"),
    "a listing index, not one offer": re.compile(
        r"(view (?:all |our |nationwide )?inventory|nationwide inventory|\bsee all\b|\bview all\b|\bver todos\b|"
        r"\bver mas\b|mas anuncios|more listings|vehiculos del profesional|se abre en una nueva ventana|"
        r"opens? in a new (?:window|tab)|\bdistribuidor de\b|dealer locator)"),
    "an accessory": re.compile(
        r"\b(accesorios?|accessor(?:y|ies)|amplificador\w*|amplifiers?|subwoofers?|fundas?|alfombrillas?|"
        r"floor mats?|llaveros?|keychains?|pegatinas?|stickers?|decals?|emblemas?|emblems?|carro de mano|"
        r"hand trucks?|tumbonas?|"
        # cheapest-monitor EN (2026-10-14): «Nuevo Adaptador de CA Monitor — 170», «Adaptador 19V para LG 27UK650-W —
        # 17.91», «19.5v3.3a Adapter for LG — 26.35» were offered as monitors; «with adapter» stays (`_WITH_BEFORE`)
        r"adaptador(?:es)?|adapters?|cargador(?:es)?|chargers?|power suppl(?:y|ies)|fuentes? de alimentacion)\b"),
    "an add-on, not the item": re.compile(
        r"\b(insurance|accidental damage|extended warranty|garantia extendida|protection plan|"
        r"seguro (?:de|contra) (?:accidentes|robo|danos))\b"),
}

#: Raw-title markers (case matters): the HO / H0 model-railway scale.
CASE_SENSITIVE: dict[str, re.Pattern] = {
    "a toy or scale model": re.compile(r"\b(HO|H0)\b"),
}

#: A request for a VEHICLE: the category that carries its own floor, its own part nouns and its core attributes.
VEHICLE_ASK = re.compile(
    r"\b(coches?|autos?|automovil\w*|vehiculos?|turismos?|cars?|vehicles?|suvs?|todoterrenos?|furgonetas?|vans?|"
    r"camionetas?|pickups?|trucks?|motos?|motocicletas?|motorcycles?|motorbikes?|scooters?)\b")

#: A vehicle ask is about BUYING one: «alquiler de coches» and «seguro de coche» are services, and the vehicle rules
#: (a floor, a make or a year) rejected every rental office and insurer of four recorded sheets.
BUYING = re.compile(r"\b(segunda mano|usad[oa]s?|used|de ocasion|comprar|compro|buy|buying|for sale|en venta|"
                    r"seminuevos?|pre-?owned|km ?0)\b")
NOT_BUYING = re.compile(r"\b(alquil\w*|rent\w*|seguros?|insurance|insurer\w*|leasing|renting)\b")

#: Part nouns that only mean «a part» when a VEHICLE was asked (a «Fender» is a guitar maker).
VEHICLE_PARTS = re.compile(
    r"\b(guardabarros|paragolpes|parachoques|retrovisor\w*|faros?|pilotos? traseros?|llantas?|neumaticos?|"
    r"bocinas?|claxon|gato|alternador|embrague|motor de arranque|capo|aletas?|bumpers?|fenders?|headlights?|"
    r"tail ?lights?|grilles?|hubcaps?|rims?|tires?|tyres?|horns?|jack|mirrors?)\b")

#: The lowest price a whole vehicle is plausibly listed at (any of €/$/£): below it, the row is a part, a toy or
#: a placeholder («€ 1»). Measured: the junk sat at 1–224 (ES) and 2.71–534 (EN), the real cars at 1,500 and up.
VEHICLE_FLOOR = 600.0

#: Makes, cars and motorcycles: a vehicle row names one, or a model year, somewhere (title, subtitle, url).
MAKES = frozenset((
    "abarth", "acura", "alfa", "alpine", "aprilia", "aston", "audi", "bentley", "benelli", "bmw", "buick", "byd",
    "cadillac", "chevrolet", "chevy", "chrysler", "citroen", "cupra", "dacia", "daelim", "daewoo", "daihatsu",
    "dodge", "ds", "ducati", "ferrari", "fiat", "ford", "genesis", "gmc", "harley", "honda", "hummer", "hyundai",
    "infiniti", "isuzu", "iveco", "jaguar", "jeep", "kawasaki", "kia", "ktm", "kymco", "lada", "lamborghini",
    "lancia", "land", "lexus", "lincoln", "lotus", "maserati", "mash", "mazda", "mercedes", "mg", "mini",
    "mitsubishi", "nissan", "opel", "peugeot", "piaggio", "polestar", "porsche", "ram", "renault", "rover",
    "saab", "seat", "skoda", "smart", "ssangyong", "subaru", "suzuki", "sym", "tesla", "toyota", "triumph",
    "vauxhall", "vespa", "volkswagen", "volvo", "vw", "wottan", "yamaha",
))

#: Never a subject: words written capitalised in a request that name a time, not a thing (ES + EN).
NOT_A_SUBJECT = frozenset((
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
    "noviembre", "diciembre", "lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo",
    "january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
    "november", "december", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "hey", "hola", "oye", "please", "porfa", "zaelar",
))

#: A sigla that names a CATEGORY or a SPEC, never one of the things he offered by name («Samsung o LG»): read
#: only when it stands beside a found name (`asked.subjects`).
NOT_A_SUBJECT_SIGLA = frozenset((
    "suv", "tv", "pc", "4k", "hd", "fhd", "uhd", "led", "oled", "lcd", "ips", "usb", "ssd", "hdd", "ram", "gps",
    "tdi", "tdci", "hdi", "gti", "abs", "ok", "ia", "ai", "dvd", "cd", "bd", "ev", "phev", "awd", "cvt", "diy",
))

#: One kind of thing, named in ES and EN: a word he RULED OUT in one language rules out the row that says it in the
#: other (`search/excluded.py`). hotel-under-15-days ES (2026-10-14): «no hostales ni albergues» stood while «Hostel
#: Ikigai», «Urban Cube Hostel Sevilla» and «The Nomad Hostel&Pension» were offered as four-star hotels. Accent-free
#: singular stems; a family is listed only when a recorded sheet carried it.
SAME_THING: tuple[tuple[str, ...], ...] = (
    ("hostal", "hostel", "albergue"),
    ("pension", "guesthouse", "guest house"),
)
