"""search/spec_words.py — the ATTRIBUTE FAMILIES a stated spec belongs to, ES + EN (V2-782 T3.3). Data only.

Read by `search/spec_fit.py`. A family is one attribute with mutually exclusive values: a TV panel is OLED or QNED,
never both; a watch movement is automatic or quartz. When his words name a value, a row whose title or facts name
ANOTHER value of the same family — and not his — contradicts what he asked. Measured 2026-10-14: search-buy-tv ES
(«OLED» → «LG 55QNED70B6C», twice after the correction), search-buy-watch ES («un Seiko automático, uno solo» →
«Pack 2 Relojes Seiko», «Majesta HAQ», «Seiko Solar»).

Every pattern is matched over accent-free lowercase text (`asked.norm`) with letter boundaries only, so a value
inside a model code still reads («55qned70b6c», «oled55c54la»). `needs`: a family whose words are shared with
other domains («automático» is also a gearbox, «eléctrico» a guitar and a car) applies only when the request names
its domain. A value listed here is a FACT about the thing, never a taste.
"""
from __future__ import annotations

_TV = r"tv|tele|teles|televisor\w*|television\w*|smart tv|monitor\w*|pantalla\w*|screen\w*|display\w*"
_WATCH = (r"reloj\w*|watch\w*|cronografo\w*|chronograph\w*|seiko|citizen|casio|orient|tissot|omega|rolex|hamilton|"
          r"longines|tudor|swatch|oris|certina|bulova|timex|invicta|breitling|tag heuer|junghans|festina|lotus|"
          r"viceroy|sinn|doxa|glycine|vostok|raketa")
_VEHICLE = (r"coches?|car|cars|autos?|vehiculos?|vehicles?|furgonetas?|vans?|suv|todoterreno|camionetas?|trucks?|"
            r"pickups?|motos?|motocicletas?|motorcycles?|scooters?|patinetes?|turismos?|sedan|berlina|hatchback")
_INSTRUMENT = r"guitarras?|guitars?|bajos?|bass|pianos?|violin\w*|ukelele\w*|ukulele\w*|instrumentos?|instruments?"

#: name → {"needs": the domain words the request must carry (or None), "values": value → its patterns}.
FAMILIES: dict[str, dict] = {
    "panel": {"needs": _TV, "values": {
        "OLED": (r"oled", r"qd-oled", r"qd oled", r"woled", r"oled evo"),
        "QNED": (r"qned",),
        "QLED": (r"qled", r"neo qled"),
        "Mini-LED": (r"mini-led", r"mini led", r"miniled", r"mled"),
        "LED/LCD": (r"led", r"lcd", r"ips"),
    }},
    "movement": {"needs": _WATCH, "values": {
        "automatic": (r"automatic[oa]s?", r"automatic", r"automatique", r"self-winding", r"self winding",
                      r"auto-winding", r"autowinding"),
        "quartz": (r"cuarzo", r"quartz", r"haq", r"solar", r"eco-drive", r"eco drive", r"kinetic"),
        "manual winding": (r"cuerda manual", r"carga manual", r"manual wind\w*", r"hand-wound", r"hand wound",
                           r"hand-wind\w*", r"hand wind\w*"),
    }},
    "transmission": {"needs": _VEHICLE, "values": {
        "automatic": (r"automatic[oa]s?", r"automatic", r"cambio automatico", r"auto trans\w*", r"dsg", r"cvt"),
        "manual": (r"cambio manual", r"caja manual", r"transmision manual", r"manual transmission",
                   r"manual gearbox", r"stick shift", r"\d-speed manual", r"(?:cambio|transmision|transmission|"
                   r"gearbox|caja de cambios)\W{1,3}manual"),
    }},
    "fuel": {"needs": _VEHICLE + r"|diesel|gasolina|gasoline|petrol|hibrid\w*|hybrid\w*", "values": {
        "diesel": (r"diesel", r"gasoleo", r"tdi", r"tdci", r"hdi", r"bluehdi", r"crdi", r"dci", r"cdi", r"d4d",
                   r"jtd", r"multijet"),
        "petrol": (r"gasolina", r"gasoline", r"petrol", r"tsi", r"tfsi", r"gdi"),
        "hybrid": (r"hibrid[oa]s?", r"hybrids?", r"phev", r"hev", r"plug-in", r"enchufable"),
        "electric": (r"electric[oa]s?", r"electric", r"bev", r"100% electric\w*"),
    }},
    "instrument": {"needs": _INSTRUMENT, "values": {
        "acoustic": (r"acustic[oa]s?", r"acoustic", r"electroacustic[oa]s?", r"electro-acoustic", r"clasica",
                     r"classical"),
        "electric": (r"electric[oa]s?", r"electric"),
    }},
}

#: A value that IS another one too: a Mini-LED, QLED or QNED panel is an LED-lit LCD, so it serves an «LED» ask
#: (and never an «OLED» one).
SATISFIES: dict[str, dict[str, frozenset]] = {
    "panel": {"Mini-LED": frozenset({"LED/LCD"}), "QLED": frozenset({"LED/LCD"}), "QNED": frozenset({"LED/LCD"})},
}

#: A value named right after one of these is ruled OUT, never asked: «no QNED», «ni LED», «descarta el cuarzo».
NEGATED_BEFORE = (r"(?:\b(?:no|ni|sin|nada de|not|nor|no more|without|except|excepto|salvo|menos|descarta\w*|"
                  r"discard\w*|exclude\w*|excluye\w*|evita\w*|avoid\w*|fuera)\s+(?:(?:el|la|los|las|un|una|de|a|an|"
                  r"the|any|ningun\w*)\s+)?)$")
#: A later value joins the asked one when tied to it («diésel o híbrido», «OLED or QLED») or wanted in so many words.
JOINED_BEFORE = r"^\s*(?:,|/|o|u|or|y|and|e|y/o|and/or)\s*$"
WANTED_BEFORE = (r"(?:\b(?:pedi|pido|quiero|queria|busco|buscaba|me vale\w*|tambien|prefiero|mejor|solo|solamente|"
                 r"tiene que ser|que sea|asked for|i want\w*|want\w*|looking for|also|instead|rather|only|"
                 r"has to be|must be|prefer\w*)\s+(?:(?:un|una|el|la|a|an|the)\s+)?(?:\w+\s+)?)$")

#: How many items one row is: «Pack 2 Relojes», «pack de 2», «2-pack», «lote de 3», «set of 4», «2 unidades».
NUMBER_WORDS = {"dos": 2, "two": 2, "tres": 3, "three": 3, "cuatro": 4, "four": 4, "cinco": 5, "five": 5,
                "seis": 6, "six": 6, "pair": 2, "par": 2, "pareja": 2, "duo": 2, "twin": 2}
_N = r"(\d{1,2}|" + "|".join(NUMBER_WORDS) + r")"
PACK = (rf"\b(?:pack|lote|set|juego|kit|bundle)\s+(?:de\s+|of\s+)?{_N}\b(?!\s*(?:%|mm|cm|kg|gb|tb|w\b|v\b|"
        rf"pulgadas|\"|in\b|meses|months|anos|years))",
        rf"\b{_N}[\s-]?(?:pack|unidades|uds|units|pcs|piezas|relojes|watches|televisores|tvs)\b",
        r"\b(pareja|par|pair|duo|twin)\s+(?:de\s+|of\s+)?(?:relojes|watches|televisores|tvs|pack)\b",
        r"\b(lote|lot of|job lot)\b")
#: He asked for ONE item, in so many words.
SINGLE = (r"\b(?:un solo|uno solo|una sola|solo uno|solo una|uno nada mas|una nada mas|solamente uno|solamente una|"
          r"a single|just one|only one|one only|single unit|unidad suelta|una unidad|one unit|no (?:un |una )?(?:pack|"
          r"lote)|not a (?:pack|lot|set)|sin pack)\b")

#: Capacities a request states with a unit: «lavadora de 8 kg», «4.5 cu ft». name → (unit pattern, tolerance).
#: A number before the unit; «8/5 kg» (a washer-dryer: wash / dry) states both.
MEASURES: dict[str, tuple[str, float]] = {
    "kg": (r"kg|kgs|kilos?|kilogramos?|kilograms?", 0.5),
    "cu ft": (r"cu\.?\s?ft\.?|cubic f(?:ee|oo)t|pies cubicos|ft3|ft³", 0.25),
}
#: A fact whose label names one of these is another quantity of the same unit (the machine's own weight, the dryer).
MEASURE_OTHER_LABEL = r"\b(?:peso|weight|secado|drying|dryer|secadora|dimensions?|dimensiones|envio|shipping)\b"
#: Beside the asked number, it is a floor or a cap, not an exact capacity.
MEASURE_FLOOR = (r"\b(?:al menos|como minimo|minimo|at least|minimum|min\.?|no menos de|desde)\s+(?:de\s+)?$",
                 r"^\s*(?:o mas|o superior|or more|or larger|or bigger|and up|y mas|\+|para arriba|en adelante|minimo|min\b)")
MEASURE_CAP = (r"\b(?:hasta|como mucho|como maximo|maximo|max\.?|up to|at most|no mas de|under|menos de)\s+(?:de\s+)?$",
               r"^\s*(?:o menos|or less|or smaller|como maximo|max\b|maximo)")
