"""A SYNTHETIC directory with the shape of a real one (V2-854 F0) — no person in it exists.

Built from what was MEASURED on a real ~2 900-entry directory (counts and patterns only, never a name):

  · 94 % people, 6 % WhatsApp groups (no members known); 0 companies, 0 agents; 2 favorites, 2 with aliases;
  · reach: 58 % phone only, 37 % e-mail only, 3 % phone + e-mail, 1 % a WhatsApp chat (most `@lid`, not a phone),
    <1 % no phone, no e-mail and no channel (UNCLASSIFIED), a single Telegram chat;
  · names: 26 % one word, 35 % two, 20 % three, 19 % four or more; 20 % all lowercase; 16 % of the e-mail-only
    ones named like an address («name.surname», digits);
  · 55 % of the people share their first word with someone else, the commonest first word by 3 % of the people;
    a first word is a non-first word elsewhere often («Manu <Name>»); phonetic twins among first words
    (qu/k, i/y, c/k, a silent h);
  · one person split across records: shared phones (≈1 %), shared e-mails (≈0.5 %), a WhatsApp record and an
    e-mail-only Google record of the same person, never linked.

The population is generated (seeded, deterministic); the CASE rows are placed by hand, with stable ids («fav-rakel», «tomeu-none»),
so a test says «the favorite» and never a row number. Every phone is in the UK's drama range (+44 7700 900xxx),
every address on an RFC 2606 domain, every chat id made up — nothing here can reach anybody.
"""
from __future__ import annotations

import random
import time

DAY = 86400.0

# ── synthetic pools (common given names, invented surnames; none of the case words below) ─────────────────────
_FIRST = ("Ana Marta Laura Sara Elisa Nuria Irene Clara Julia Noelia Rosa Inés Alba Silvia Beatriz Sonia Patricia "
          "Cristina Teresa Isabel Mónica Eva Paula Montse Gemma Susana Victoria Lorena Natalia Rocío Marc Sergi "
          "Albert Jaume Xavi Oriol David Javier Carlos Miguel Antonio Manuel Francisco Luis Andrés Rafael Álvaro "
          "Diego Iván Óscar Rubén Adrián Hugo Martín Bruno Gonzalo Íñigo Joan Ferran Guillem Pol Arnau "
          "Emma Olivia Grace Chloe Hannah Amy Laura Ruth Paul Mark Peter Simon Adam Daniel Thomas James George "
          "Henry Oliver Jack Harry Sam Ben Alex").split()
_SURNAME = ("Albar Brunet Carreño Duval Esquer Fabra Galdón Hervás Ibarra Juncosa Lledó Marbán Noguer Oller Pradas "
            "Quevedo Ribas Sallent Tamarit Urgell Valdés Xirau Yáñez Zurita Abellán Bonet Casals Dalmau Escrivà "
            "Ferrán Gisbert Horta Isern Jover Llorens Mestre Nadal Ortega Pujadas Roca Soler Torrent Vallès "
            "Ashby Blake Carver Dunmore Ellery Farrow Gaskell Hollis Ingram Jessop Kendrick Lowell Marlow Norwood "
            "Oakley Pember Quill Radley Stroud Thorne").split()
_CONTEXT = ("gimnasio", "trabajo", "cole", "vecina", "fontanero", "academia", "pádel", "office", "uni", "taller")
_GROUPS = ("Cumple 40", "Pádel domingos", "Cena viernes", "Viaje Lisboa", "Comunidad escalera B", "Running club",
           "Family", "Book club", "Despedida", "Fútbol martes", "Clase de inglés", "Boda", "Barbacoa", "Equipo",
           "Vecinos", "Reunión antiguos alumnos")

# ── the case rows — WHERE confusion lives (V2-854) ─────────────────────────────────────────────────────────────
_SEQ = [0]
_NOW = [0.0]


def _tel() -> str:
    _SEQ[0] += 1
    return f"+44 7700 900{_SEQ[0]:03d}"


def _person(cid: str, name: str, *, phone: bool = False, email: str = "", wa: str = "", tg: str = "",
            favorite: bool = False, relation: str = "", source: str = "google", days_ago: float | None = None,
            kind: str = "person", tel: str = "") -> dict:
    chans = []
    seen = _NOW[0] - days_ago * DAY if days_ago is not None else 0.0
    if wa:
        chans.append({"platform": "whatsapp", "handle": wa, "chatId": wa, "source": "observed",
                      "volume": 12 if days_ago is not None else 0, "last_seen": seen})
    if tg:
        chans.append({"platform": "telegram", "handle": tg, "chatId": tg.lstrip("@"), "source": "observed",
                      "volume": 12 if days_ago is not None else 0, "last_seen": seen})
    number = tel or (_tel() if phone else "")
    return {"id": cid, "kind": kind, "name": name, "phone": number, "email": email, "channels": chans,
            "favorite": favorite, "relation": relation, "aliases": [], "groups": [], "source": source,
            "city": "", "address": "", "notes": "", "preferred": "", "parentId": None}


def _lid(n: int) -> str:
    return f"9000000000{n:05d}@lid"


def _cases() -> list[dict]:
    """The hand-placed rows. Spanish and English, each a pattern measured on the real directory."""
    return [
        # «Raquel»: nine people carry the word, the one he means is saved with a near spelling and is his favorite
        # (WhatsApp by a `@lid` chat), and the same person also exists as an e-mail-only Google record.
        _person("fav-rakel", "Rakel Ibarz", phone=True, wa=_lid(1), favorite=True, source="whatsapp", days_ago=2),
        _person("rakel-mail", "raquel.ibarzmolins", email="raquel.ibarz@example.com"),
        _person("raquel-1", "Raquel Soto", phone=True),
        _person("raquel-2", "Raquel Peña Albar", phone=True),
        _person("raquel-3", "Manu Raquel", phone=True),
        _person("raquel-4", "Raquel Vidal Rius", email="rvidal@example.net"),
        _person("raquel-5", "raquel", phone=True),
        _person("raquel-6", "Raquel Gimnasio", phone=True),
        _person("raquel-7", "Raquel Ofi", phone=True, email="raquel.ofi@example.org"),
        _person("raquel-8", "Raquel Lago", phone=True),
        _person("raquel-9", "Mari Raquel Pons", phone=True),
        # «Jordi»: an i/y twin he talks to this week among three background namesakes, one of them e-mail only.
        _person("active-jordy", "Jordy Mas", phone=True, wa=_lid(2), source="whatsapp", days_ago=3),
        _person("jordi-1", "Jordi Puig", phone=True),
        _person("jordi-mail", "Jordi Font", email="jfont@example.com"),
        _person("jordi-3", "Jordi Serra Bonet", phone=True),
        # «Elena»: a silent h — his favorite is «Helena», two background Elenas.
        _person("fav-helena", "Helena Rius", phone=True, favorite=True),
        _person("elena-1", "Elena Sanz", phone=True),
        _person("elena-2", "elena mir", phone=True),
        # «Lucía»: a mail can only go to the one with an address.
        _person("lucia-active", "Lucía Prats", phone=True, wa=_lid(3), source="whatsapp", days_ago=5),
        _person("lucia-mail", "Lucía Bosch", email="lucia.bosch@example.org"),
        _person("lucia-3", "Lucia Coll", phone=True),
        # «Tomeu»: one of the two has no phone, no e-mail and no channel — UNCLASSIFIED, never a recipient.
        _person("tomeu-none", "Tomeu Bauzà"),
        _person("tomeu-tel", "Tomeu Riera", phone=True),
        _person("noel-none", "Noel Quill"),
        _person("noel-tel", "Noel Farrow", phone=True),
        # A company and the people who share its word.
        _person("company-ortiz", "Ferretería Ortiz", phone=True, kind="company"),
        _person("ortiz-1", "Marta Ortiz", phone=True),
        _person("ortiz-2", "Pere Ortiz Casals", email="portiz@example.net"),
        # A compound first name, said split by the voice.
        _person("mother-maricarmen", "Maricarmen Soler", phone=True, relation="mother"),
        _person("carmen-1", "Carmen Vives", phone=True),
        _person("maripau-1", "Mari Pau Roig", phone=True),
        # «Pablo»: four background namesakes, nobody closer — the question, then his pick, once.
        _person("pablo-1", "Pablo Hervás", phone=True),
        _person("pablo-2", "Pablo Elastic", phone=True),
        _person("pablo-3", "Psm Pablo Buso", phone=True),
        _person("pablo-4", "Carmen Mamá de Pablo", phone=True),
        # English: c/k — his favorite «Katherine» (Telegram) among five background «Catherine»s.
        _person("fav-katherine", "Katherine Hale", tg="@khale_fx", favorite=True, source="telegram"),
        _person("catherine-1", "Catherine Moss", phone=True),
        _person("catherine-2", "Catherine Webb", email="cwebb@example.com"),
        _person("catherine-3", "Catherine Price", phone=True),
        _person("catherine-4", "catherine b", phone=True),
        _person("catherine-5", "Catherine Doyle", phone=True),
        # English: a silent h — «John», the one he talks to is «Jon».
        _person("active-jon", "Jon Reyes", phone=True, wa=_lid(4), source="whatsapp", days_ago=1),
        _person("john-1", "John Fox", phone=True),
        _person("john-mail", "John Hart", email="jhart@example.org"),
        # English: three background «Owen»s, all reachable the same way — the question, then his pick, once.
        _person("owen-1", "Owen Hart", phone=True),
        _person("owen-2", "Owen Stroud", phone=True),
        _person("owen-3", "owen b", phone=True),
        # English: a mail and a WhatsApp each pick their own «Megan».
        _person("megan-tel", "Megan Ford", phone=True),
        _person("megan-mail", "Megan Clark", email="mclark@example.net"),
        # English: a company and a person who share its word.
        _person("company-thorne", "Thorne Plumbing Ltd", phone=True, kind="company", email="desk@example.com"),
        _person("thorne-1", "Amy Thorne", phone=True),
        # Groups he already has on WhatsApp: a chat with an identity, written to as one recipient.
        _group("group-padel", "Pádel domingos", 1),
        _group("group-family", "Family", 2),
    ]


def _group(cid: str, name: str, n: int) -> dict:
    jid = f"1203630000000{n:05d}@g.us"
    return {"id": cid, "kind": "group", "subtype": "group", "platform": "whatsapp", "name": name, "members": [],
            "membersKnown": False, "phone": "", "email": "", "aliases": [], "groups": [], "favorite": False,
            "source": "whatsapp", "city": "", "address": "", "notes": "", "preferred": "", "parentId": None,
            "channels": [{"platform": "whatsapp", "handle": "", "chatId": jid, "source": "observed", "volume": 0,
                          "last_seen": 0.0}]}


#: The words the case rows own: the generated population never carries them, so a count about «Raquel» is the
#: case's count and not the luck of the generator.
_CASE_WORDS = {"raquel", "rakel", "jordi", "jordy", "elena", "helena", "lucia", "tomeu", "ortiz", "maricarmen",
               "carmen", "mari", "pau", "pablo", "katherine", "catherine", "jon", "john", "megan", "padel",
               "family", "thorne", "plumbing", "noel", "owen"}


def _fold(s: str) -> str:
    import unicodedata
    n = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(ch for ch in n if not unicodedata.combining(ch)).lower()


def _population(rng: random.Random, people: int, groups: int) -> list[dict]:
    first = [f for f in _FIRST if _fold(f) not in _CASE_WORDS]
    sur = [s for s in _SURNAME if _fold(s) not in _CASE_WORDS]
    gnames = [g for g in _GROUPS if not set(_fold(g).split()) & _CASE_WORDS]
    weights = [1.0 / (i + 1) ** 0.9 for i in range(len(first))]          # a few first names are very common
    out: list[dict] = []
    shared_tels: list[str] = []
    shared_mails: list[str] = []
    for i in range(people):
        f = rng.choices(first, weights)[0]
        words = rng.choices((1, 2, 3, 4), (26, 35, 20, 19))[0]
        name = " ".join([f] + rng.sample(sur, k=min(words - 1, 2)) + ([rng.choice(_CONTEXT)] if words == 4 else []))
        reach = rng.choices(("phone", "email", "both", "wa", "none"), (58, 37, 3, 1, 1))[0]
        c = _person(f"p{i:03d}", name, phone=reach in ("phone", "both", "wa"),
                    email=(f"{_fold(name).replace(' ', '.')}{i}@example.com" if reach in ("email", "both") else ""),
                    wa=_lid(100 + i) if reach == "wa" else "", source="whatsapp" if reach == "wa" else "google",
                    days_ago=rng.choice((4, 40, 300)) if reach == "wa" else None)
        if reach == "email" and rng.random() < 0.16:                        # named like the address it came from
            c["name"] = c["email"].split("@", 1)[0]
        elif rng.random() < 0.2:
            c["name"] = c["name"].lower()
        # One person, two records: a few rows reuse an earlier phone or address (never linked).
        if c["phone"] and shared_tels and rng.random() < 0.012:
            c["phone"] = rng.choice(shared_tels)
        elif c["phone"]:
            shared_tels.append(c["phone"])
        if c["email"] and shared_mails and rng.random() < 0.012:
            c["email"] = rng.choice(shared_mails)
        elif c["email"]:
            shared_mails.append(c["email"])
        out.append(c)
    for g in range(groups):
        out.append(_group(f"g{g:03d}", f"{rng.choice(gnames)} {2015 + g % 10}", 100 + g))
    return out


def build(*, people: int = 300, groups: int = 18, seed: int = 854, now: float | None = None) -> list[dict]:
    """The whole directory: the case rows first, then the generated population. Deterministic for a seed and a
    `now` (traffic is dated relative to it: «talked to three days ago» must stay three days ago)."""
    _SEQ[0] = 0
    _NOW[0] = time.time() if now is None else float(now)
    rng = random.Random(seed)
    rows = _cases()
    rows += _population(rng, people, groups)
    return rows


def install(store_mod, data_mod, rows: list[dict] | None = None) -> list[dict]:
    """Write the directory into an ISOLATED contacts store (the caller already pointed `store.DATA_DIR` at a temp
    dir) through the store's own `save`, every row through `model.normalize` as an import would."""
    from widgets.contactos import model
    rows = [model.normalize(dict(r)) for r in (rows if rows is not None else build())]
    db = data_mod.load_db()
    db["contacts"] = rows
    db["next_id"] = len(rows) + 1
    store_mod.save(data_mod.WIDGET_ID, db)
    return rows
