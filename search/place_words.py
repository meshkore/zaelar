"""search/place_words.py — the PLACES a row may name, grouped by metropolitan area (V2-782 T3.3). Data only.

Read by `search/place_fit.py`. Each entry is one metro: its city (with its other spellings, ES/EN) and the separate
municipalities around it. A suburb is a DIFFERENT place from its city unless he widened the ask («y alrededores»,
«area», «near»): search-rent-apartment US (2026-10-14) offered Round Rock and Manor rows as «Austin».

Not a geocoder: a short list of the cities our use cases name, matched on accent-free text. A place missing here
is simply not judged. The two US/ES address shapes («Pflugerville, TX», «28100 Alcobendas») are read by the
module, not listed.
"""
from __future__ import annotations

#: city names (first is canonical) → suburbs. Every name accent-free, lowercase.
METROS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("austin",), ("round rock", "pflugerville", "cedar park", "georgetown", "leander", "manor", "kyle", "buda",
                   "hutto", "lakeway", "bee cave", "dripping springs", "san marcos", "elgin")),
    (("new york", "nueva york", "nyc", "manhattan"), ("jersey city", "hoboken", "newark", "yonkers", "white plains",
                                                       "stamford")),
    (("san francisco",), ("oakland", "berkeley", "daly city", "san mateo", "south san francisco", "san jose",
                               "palo alto", "fremont", "hayward", "walnut creek", "sausalito", "lodi", "pleasanton")),
    (("los angeles",), ("santa monica", "pasadena", "burbank", "glendale", "long beach", "inglewood",
                             "torrance", "anaheim", "irvine")),
    (("san diego",), ("chula vista", "oceanside", "escondido", "carlsbad", "el cajon")),
    (("chicago",), ("evanston", "oak park", "naperville", "schaumburg", "cicero")),
    (("miami",), ("miami beach", "hialeah", "coral gables", "fort lauderdale", "doral", "homestead")),
    (("boston",), ("cambridge", "somerville", "quincy", "brookline", "newton", "medford")),
    (("seattle",), ("bellevue", "redmond", "tacoma", "kirkland", "everett", "renton")),
    (("denver",), ("aurora", "lakewood", "boulder", "littleton", "englewood")),
    (("houston",), ("sugar land", "the woodlands", "pearland", "katy", "baytown")),
    (("dallas",), ("fort worth", "plano", "irving", "arlington", "garland", "frisco", "mckinney")),
    (("madrid",), ("alcobendas", "getafe", "leganes", "mostoles", "alcorcon", "fuenlabrada", "pozuelo de alarcon",
                   "las rozas", "majadahonda", "boadilla del monte", "torrejon de ardoz", "coslada",
                   "rivas-vaciamadrid", "rivas vaciamadrid", "san sebastian de los reyes", "tres cantos", "parla",
                   "alcala de henares", "valdemoro", "pinto", "arganda del rey", "collado villalba", "aranjuez")),
    (("barcelona",), ("l'hospitalet", "hospitalet de llobregat", "badalona", "sabadell", "terrassa", "sant cugat",
                      "cornella", "el prat de llobregat", "castelldefels", "mataro", "granollers", "sitges")),
    (("valencia",), ("torrent", "paterna", "burjassot", "mislata", "sagunto", "manises", "alboraya", "catarroja",
                     "gandia")),
    (("sevilla", "seville"), ("dos hermanas", "alcala de guadaira", "mairena del aljarafe", "utrera")),
    (("malaga",), ("marbella", "torremolinos", "benalmadena", "fuengirola", "velez-malaga", "rincon de la victoria")),
    (("bilbao",), ("barakaldo", "getxo", "portugalete", "basauri")),
    (("zaragoza",), ("utebo", "cuarte de huerva")),
)

#: Words after which he widened the ask to the metro around the place.
WIDENED = (
    r"\b(?:y |and )?(?:alrededores|cercanias|afueras|area metropolitana|zona metropolitana|area|metro area|"
    r"greater|surrounding|surroundings|nearby|near|cerca de|around|suburbs?|periferia|provincia|"
    r"hasta ~?\d+ (?:hora|minutos?|km)|within \d+ (?:miles?|minutes?|km))\b"
)

#: US state codes, read in the «City, ST» address shape.
US_STATES = frozenset((
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME",
    "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA",
    "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
))

#: What follows a place in a listing URL's path segment («Round-Rock-Apartments», «austin-tx»).
URL_TAILS = frozenset((
    "apartments", "apartment", "apts", "homes", "houses", "rentals", "rent", "for", "real", "estate", "condos",
    "pisos", "viviendas", "alquiler", "casas", "capital", "centro", "provincia",
)) | frozenset(s.lower() for s in US_STATES)
