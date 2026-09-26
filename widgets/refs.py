"""widgets/refs.py — resolving natural-language REFERENCES to items (V2-026).

The operator speaks natural language ("mark the daemon task done", "postpone the Reddit thing"); they do NOT know a
widget item's internal ids, and a fast model that tries to guess them INVENTS them (V2-026 bug: FlashBrain emitted
`done` with `taskId="09:00–11:00"` —the time range— instead of "t_daemon"). Solution: the model passes a
natural-language REFERENCE (`item`) and HERE it is resolved to the REAL id against the widget's LIVE items.

Widget contract (OPTIONAL, in its `data.py`):

    def ref_index() -> list[dict]:
        '''Voice-referenceable items: [{"id","label","field"[,"hint"]}]. `field` = the payload key that identifies
        that item in manifest actions (e.g. "taskId" for a task, "projectId" for a project). `label` = human text for
        matching the reference (task title, project name...). Optional `hint` = extra brief context (status, time...).'''

The field to fill is read from the OWN manifest: an action says which of its payload keys names an existing item
with `"ref": "<key>"`, and failing that the V2-026 convention applies (a key whose name ends in `id`: agenda
`done`→{"taskId":...}, `drop_project`→{"projectId":...}). The reference is resolved ONLY against items whose
`field` matches that field → "discard the Atlas project" (`drop_project`→`projectId`) points to the PROJECT,
not to the "Atlas review" task. Stdlib fuzzy matching (token overlap + difflib), accent-insensitive. Returns an
AMBIGUITY/NO-MATCH signal instead of guessing (better to ask than act on the wrong item).
"""
from __future__ import annotations

import difflib
import re
import unicodedata

from . import runtime


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9ñ ]+", " ", s).strip()


_STOP = set("el la los las un una de del en al a y o que con para por mi tu su lo se me the a an of to my "
            "tarea tareas cita citas item proyecto la de lo eso esa ese esta este cosa asunto".split())


# WHEN, never WHICH — a closed class, the same shape as `_ORDINALS` and `_POS_FILLER` and for the same
# reason: resolving these is a lookup, not a judgement about intent. They are stripped from a reference that
# came out of the OPERATOR'S SENTENCE rather than out of `item`, because in a sentence a day or a month is
# the DATE of the thing, and the actions that need one declare their own `date` key for it.
# Measured (V2-708): «avisos para todas las citas del jueves» asks for every meeting on Thursday, and it
# scored the meeting TITLED «Jueves Santo» high enough to win — one reminder moved instead of the whole day.
# It only ever applies to the fallback: «borra Jueves Santo» puts that title in `item`, and there it counts.
_TEMPORAL = set("lunes martes miercoles jueves viernes sabado domingo monday tuesday wednesday thursday "
                "friday saturday sunday enero febrero marzo abril mayo junio julio agosto septiembre "
                "setiembre octubre noviembre diciembre january february march april may june july august "
                "september october november december hoy ayer manana today tomorrow yesterday tonight "
                "semana mes week month".split())


def _ref_index(widget_id: str) -> list[dict]:
    try:
        import importlib
        mod = importlib.import_module(f"widgets.{widget_id}.data")
        if hasattr(mod, "ref_index"):
            idx = mod.ref_index()
            # `label` is required too: a row without one cannot be referenced by voice, cannot be listed, and
            # would make `resolve()` break its own «NEVER raises» promise (KeyError in the exact-title pass and
            # in every candidates list).
            return [i for i in idx if isinstance(i, dict) and i.get("id") and i.get("field") and i.get("label")]
    except Exception:
        pass
    return []


def _exposes_ref_index(widget_id: str) -> bool:
    """Does this widget PUBLISH its items? (to distinguish "empty" from "does not publish" — see items_line)."""
    try:
        import importlib
        return hasattr(importlib.import_module(f"widgets.{widget_id}.data"), "ref_index")
    except Exception:
        return False


_OPTIONAL_RE = re.compile(r"opcional|optional", re.I)


def selector_is_optional(widget_id: str, action: str, key: str = "") -> bool:
    """Does this action RUN without naming an item? Read from the manifest's own prose for that payload key
    («opcional»/«optional»), which is the convention every manifest already follows.

    It lives here, and `contract.selector_for` calls it, because those two functions answering the same
    question differently is the defect V2-708 measured: `contract` said `agenda.cancel_meeting`'s selector was
    `title` while `id_field_for_action` said the action had none. One reader, one answer.
    """
    try:
        spec = ((runtime.get(widget_id) or {}).get("actions") or {}).get(action) or {}
        payload = spec.get("payload")
        if not isinstance(payload, dict):
            return False
        k = key or id_field_for_action(widget_id, action) or ""
        return bool(k) and bool(_OPTIONAL_RE.search(str(payload.get(k) or "")))
    except Exception:  # noqa: BLE001
        return False


def _collection_id_field(widget_id: str, action: str, payload: dict) -> str | None:
    """The id key of a COLLECTION this action mutates in place, when the collection declares it (V2-708).

    A widget declares its rows once, at the top of its manifest:

        "collections": {"meetings": {"id": "title", "via": {"delete": "cancel_meeting",
                                                            "patch": "update_meeting",
                                                            "put": "add_meeting"}}}

    That `id` IS the answer to «which payload key names an existing row», and it is STATIC — the objection
    that sank reading it from `ref_index()` (an empty list publishes no rows) does not apply to a
    declaration. Only the verbs that touch a row that ALREADY exists count: `put`/`post` CREATE one, and
    resolving their key against the live index would make `add_meeting` refuse every appointment whose title
    is new — the opposite defect, and a louder one.
    """
    try:
        cols = (runtime.get(widget_id) or {}).get("collections") or {}
        for col in cols.values():
            if not isinstance(col, dict):
                continue
            key = str(col.get("id") or "").strip()
            if not key or key not in payload:
                continue
            via = col.get("via") if isinstance(col.get("via"), dict) else {}
            if action in [v for k, v in via.items() if str(k).lower() not in ("put", "post")]:
                return key
    except Exception:  # noqa: BLE001
        pass
    return None


def id_field_for_action(widget_id: str, action: str) -> str | None:
    """Payload key for this action that identifies an existing item, read from the manifest. None if the action
    does not operate on a preexisting item (e.g. `add_meeting`, which CREATES one) → there is nothing to resolve.

    THREE ways to say it, and each one was added by an incident:

    1. `"ref": "<payload key>"` DECLARED in the action spec. Explicit, and the only one that works on a widget
       whose list happens to be empty right now.
    2. Failing that, the convention V2-026 wrote this module around: a payload key whose name ends in 'id'
       (`taskId`, `projectId`, `chatId`).

    The suffix alone was a NAMING assumption the widget contract never made: the docstring at the top of this
    module says `field` is «the payload key that identifies that item», not «a key whose name ends in id».
    `youtube` declares `play_item`/`remove`/`move` with the key `item` and publishes `field: "item"` (V2-465,
    built so «play the third one» could resolve) — so this function answered None, `resolve()` replied «nothing
    to resolve» and handed over an EMPTY payload no matter what the operator had said, and the widget answered
    `item_not_found`. Measured live in session `abe9942b`: «show me the first one, start it» → `play_item {}` →
    «I can't find that video in the list», over a list of five with the right rows in it.

    3. Failing both, the `id` a `collections` entry declares for the rows this action mutates in place — see
       `_collection_id_field`. Added by V2-708, measured on the agenda: five voice turns naming «the Dentist
       appointment on Thursday the 17th» produced five `cancel_meeting {}`, because `cancel_meeting` declares
       `title`/`date` (no key ends in `id`) and the manifest never declared a `ref` — while the SAME manifest
       already said `collections.meetings.id == "title"` two hundred lines up. The declaration existed; nobody
       read it.

    ⚠️ The first version of the V2-595 fix read the answer out of the widget's OWN `ref_index()`, which is where the
    field name genuinely lives — and it was WRONG, caught by its own test: that index is DATA, so an empty list
    publishes no rows and the action would quietly go back to being unresolvable exactly when the widget is
    empty. What identifies an item is a property of the ACTION, so it belongs in the manifest, which is static.
    """
    try:
        spec = ((runtime.get(widget_id) or {}).get("actions") or {}).get(action) or {}
        payload = spec.get("payload")
        if not isinstance(payload, dict) or not payload:
            return None
        declared = str(spec.get("ref") or "").strip()
        if declared and declared in payload:               # a `ref` naming a key the action does not take is noise
            return declared
        for k in payload:
            if str(k).lower().endswith("id"):
                return k
        return _collection_id_field(widget_id, action, payload)    # 3 · the collection's declared id (V2-708)
    except Exception:
        pass
    return None


# POSITION words: a CLOSED class, so resolving them is a lookup and not a judgement — the same shape as the
# four scroll directions of V2-591, never a verb table. `-1` is the last row. English pulls its weight here: the
# two labs speak different languages and «play the second one» is the same order.
# «una» is NOT here and must not come back: it is the indefinite article («pon una canción» asks for A song,
# not for song one) — `_STOP` already drops it, so an entry for it would be dead today and a wrong resolution
# the day someone "fixes" the filter.
_ORDINALS = {
    "primero": 0, "primera": 0, "primer": 0, "uno": 0, "first": 0,
    "segundo": 1, "segunda": 1, "dos": 1, "second": 1,
    "tercero": 2, "tercera": 2, "tercer": 2, "tres": 2, "third": 2,
    "cuarto": 3, "cuarta": 3, "cuatro": 3, "fourth": 3,
    "quinto": 4, "quinta": 4, "cinco": 4, "fifth": 4,
    "sexto": 5, "sexta": 5, "seis": 5, "sixth": 5,
    "septimo": 6, "septima": 6, "siete": 6, "seventh": 6,
    "octavo": 7, "octava": 7, "ocho": 7, "eighth": 7,
    "noveno": 8, "novena": 8, "nueve": 8, "ninth": 8,
    "decimo": 9, "decima": 9, "diez": 9, "tenth": 9,
    "ultimo": -1, "ultima": -1, "last": -1,
}


# Nouns that name the CONTAINER or the KIND of thing, never a particular one: «el primer VÍDEO de la LISTA»
# says nothing more than «the first one». Same idea as the generic nouns already in `_STOP` («tarea», «cita»,
# «proyecto»), kept separate because it must not weaken title matching — a title containing «vídeo» has to keep
# scoring on it. Measured live: with the card open, the model calls `play_item` with exactly this shape.
# «numero/number» is here too: «el número 3» is the position word's own label and says nothing beyond «the
# 3rd» — while a title that carries a number next to a content token («sinfonía número 9») keeps that token
# and still goes to the fuzzy matcher. «episodio/capítulo» are deliberately OUT: those nouns often carry
# numbering that is item IDENTITY, not list position («el episodio 12» may sit at row 3), and resolving it by
# position would play the wrong item — the exact failure V2-026 exists to prevent.
_POS_FILLER = set("video videos clip clips cancion canciones tema temas pista pistas track tracks song songs "
                  "lista listas playlist cola elemento elementos entrada entradas fila filas resultado "
                  "resultados foto fotos imagen imagenes mensaje mensajes list queue row rows result results "
                  "numero numeros number one ones thing things".split())


def positional(widget_id: str, action: str = "") -> bool:
    """May a reference to this widget be resolved BY POSITION («la tercera», «3»)? True unless the widget —or
    the action— declares `"positional": false`.

    This flag exists because V2-643 had no other way to say it (V2-708). The agenda deliberately declared NO
    `ref` on its meeting actions, and its test says why: position needs a VISIBLE anchor — the youtube list
    prints 1, 2, 3 beside its rows, no agenda view numbers anything, and «la tercera» over an unnumbered
    calendar would cancel an appointment nobody named. But the same absence also meant
    `id_field_for_action` answered None, so `resolve` threw away every reference the model gave and
    dispatched an empty payload: five `cancel_meeting {}` in one measured session. One declaration was
    carrying two unrelated decisions — WHICH KEY names a row, and WHETHER counting rows is meaningful — and
    the widget could not have the first without the second. Now it can.

    ⚠️ THE ACTION DECIDES OVER ITS WIDGET, in both directions (V2-747). This used to read «False anywhere
    wins», and that made a card that numbers HALF of itself unsayable: the agenda declares
    `positional: false` for the reason above — no calendar view numbers an appointment — and V2-744 then gave
    it a TASKS section that prints 1, 2, 3 beside every row and a manifest that documents «su número en la
    lista («2»)» on five actions. Measured in session 16a39050: «modifica la tarea número tres» over three
    numbered tasks he was looking at, answered with «No tengo claro a cuál te refieres». One flag was again
    carrying two decisions, this time for two halves of one card — so the specific declaration wins over the
    general one, and the widget-level flag stays the DEFAULT it always was for every action that is silent.
    """
    try:
        man = runtime.get(widget_id) or {}
        spec = (man.get("actions") or {}).get(action) or {}
        if isinstance(spec.get("positional"), bool):
            return spec["positional"]
        if man.get("positional") is False:
            return False
    except Exception:  # noqa: BLE001
        pass
    return True


def _position_ref(query: str, n: int) -> "int | None":
    """Index in the published list for a reference that is PURELY about position («the first one», «the last
    one», «3»), or None to let the fuzzy matcher decide (V2-595).

    Two shapes, and both were unreachable before: a BARE INDEX («1») is the primary interface every manifest
    documents («número 1-N o texto del título») and `_score` drops it on the floor — it discards tokens of three
    characters or fewer, so a digit scores 0 and comes back `no_match`; and an ORDINAL («el primero») matches no
    title, which is the exact phrase the operator used in the session that measured this.

    NARROW on purpose: once stop words and CONTAINER nouns are gone, the position word has to be all the
    reference carries. «el primer vídeo de la lista» says nothing but «the first one» — measured live, it is
    the exact shape the model produces — while «el primer episodio de Artemis» keeps a real content token, so
    it falls through to the fuzzy matcher and the title that matches can still win it.
    """
    if n <= 0:
        return None
    toks = [t for t in (query or "").split() if t not in _STOP and t not in _POS_FILLER]
    if len(toks) != 1:
        return None
    t = toks[0]
    # 1-based, as every manifest declares it. The digit may carry an ordinal suffix: «3º»/«1ª» reach us as
    # «3o»/«1a» (NFKD decomposes the indicator into a letter before `_norm` strips anything), and typed
    # «2nd»/«3ro» count the same. The suffix set is closed and only ever follows digits, so it collides with
    # no word.
    m = re.match(r"(\d+)(?:o|a|er|ro|do|to|mo|vo|no|st|nd|rd|th)?$", t)
    if m:
        i = int(m.group(1)) - 1
        return i if 0 <= i < n else None
    pos = _ORDINALS.get(t)
    if pos is None:
        return None
    if pos < 0:
        return n - 1
    return pos if pos < n else None


def _pos_token(toks: list[str]) -> "tuple[int, list[str]] | None":
    """`(number, the tokens that are NOT the number)` for a reference that carries a position word, else None.

    1-based as every manifest declares it, and it accepts the same three spellings `_position_ref` does: a
    bare digit, a digit with an ordinal suffix («3º» arrives as «3o»), and a word («tres», «third»). Only ONE
    may appear — two numbers in a reference is not a position, it is a title.
    """
    found, rest = None, []
    for t in toks:
        m = re.fullmatch(r"(\d+)(?:o|a|er|ro|do|to|mo|vo|no|st|nd|rd|th)?", t)
        # A DIGIT IS ALREADY THE PRINTED NUMBER; a WORD comes out of `_ORDINALS`, which is 0-based because
        # its other reader indexes a list with it. Mixing the two conventions here made «la tarea número
        # tres» resolve to the row numbered 2 — the one place where being off by one is indistinguishable
        # from working, since both rows exist.
        n = int(m.group(1)) if m else (None if _ORDINALS.get(t) is None else _ORDINALS[t] + 1)
        if n is None or n < 1:                        # «el último» has no printed number to look up
            rest.append(t)
            continue
        if found is not None:
            return None
        found = n
    return None if found is None else (found, rest)


def _numbered_ref(query: str, idx: list[dict]) -> "tuple[list[dict], bool] | None":
    """`(rows, ambiguous)` for a reference that names a row BY THE NUMBER PRINTED BESIDE IT, else None (V2-747).

    `_position_ref` above resolves a position against the INDEX ORDER, which is the right answer for a single
    flat list (a search result, a queue) and the wrong one for a card that prints several numbered lists: the
    agenda's tasks restart at #1 in every list, so «la tarea 3» over «General: 2 · Obra: 3» would land on the
    flat third row — Obra #1 — and silently modify the wrong task. A number that means two things is the
    cheapest possible way to touch the wrong item, which is the one thing this module exists to prevent.

    So a widget that NUMBERS ITS ROWS publishes the number (`no`) and the section it prints it under
    (`group`), and the lookup is exact:
      · the reference must carry ONE position word and nothing else but, optionally, the group's name;
      · leftover tokens that match no group are CONTENT — «el episodio 12 de Artemis» falls through to the
        fuzzy matcher, which is the V2-026 distinction `_POS_FILLER` already draws;
      · one row with that number → resolved; several (same number in two lists, no group named) → ASK,
        with the groups as the menu, because he can answer that in three words.

    Returns None whenever the index does not publish numbers, so every widget that does not is untouched.
    """
    rows = [i for i in idx if isinstance(i.get("no"), int)]
    if not rows:
        return None
    toks = [t for t in (query or "").split() if t not in _STOP and t not in _POS_FILLER]
    got = _pos_token(toks)
    if not got:
        return None
    want, rest = got
    hit = [i for i in rows if i["no"] == want]
    if not hit:
        return None                                   # no row carries that number → let the matcher try
    if rest:
        groups = {str(i.get("group") or "") for i in rows if i.get("group")}
        named = [g for g in groups if _covered(rest, _norm(g).split()) >= 1.0]
        if len(named) > 1:
            return [], True                           # he named a group and it matched two: ask
        if not named:
            return None                               # the leftovers are CONTENT, not a group → fuzzy match
        hit = [i for i in hit if str(i.get("group") or "") == named[0]]
        if not hit:
            return [], True                           # that list has no row with that number
    return hit, len(hit) > 1


def position_index(ref: str, n: int) -> "int | None":
    """The PUBLIC name of `_position_ref`, for a widget that resolves its own items (V2-677).

    `widgets/imagenes/data.py::_resolve` matched a spoken reference against the TITLE and the SITE and
    nothing else, so «la primera», «the first one», «el tercero» and «the last one» all resolved to
    NOTHING — in either language — while a bare digit worked. Measured live 2026-09-11 (session e896f596):
    the operator asked for one of six pictures and `select` answered «dime cuál: un número o parte del
    título» over a set whose titles were all news headlines.

    A widget that owns its own resolution (because it resolves against data the generic path cannot see)
    still has no reason to own POSITION, which means the same thing everywhere. Exported rather than
    copied: a second ordinal table is how the two would come to disagree.
    """
    return _position_ref(_norm(ref or ""), n)


def _covered(needles: list[str], hay: list[str]) -> float:
    """Fraction of `needles` that `hay` accounts for — exact, substring, or a close typo."""
    if not needles:
        return 0.0
    hits = 0.0
    for t in needles:
        if t in hay or any(t in h or h in t for h in hay):
            hits += 1
        elif difflib.get_close_matches(t, hay, n=1, cutoff=0.82):
            hits += 0.8
    return hits / len(needles)


def _coverage(ref_n: str, label_n: str) -> float:
    """The better of the two coverages, 0..1 — how much of the label he named, or of the reference the label
    accounts for. `_score` weighs it against the raw ratio; on its own it is the FLOOR an unnamed reference
    has to clear (see `resolve`)."""
    r_tokens = [t for t in (ref_n or "").split() if t not in _STOP and len(t) > 2]
    l_tokens = [t for t in (label_n or "").split() if t not in _STOP]
    if not r_tokens:
        return 0.0
    return max(_covered(r_tokens, l_tokens), _covered([t for t in l_tokens if len(t) > 2], r_tokens))


def _score(ref_n: str, label_n: str) -> float:
    """How well a spoken reference names this label. Coverage counts BOTH WAYS (V2-708).

    The one-way version divided by the length of the REFERENCE, so every extra word the operator said made
    the right row score LOWER. Measured: «the Dentist appointment on Thursday the 17th» against the label
    «Dentist» covers 1 of 4 reference tokens → 0.25·2 + 0.3 = 0.8, under the 1.0 floor → `no_match`, over an
    index that held exactly that appointment. Said plainly: the more precisely he identified it, the less
    likely it resolved — and «Dentist» alone worked. That is backwards.

    A label the reference CONTAINS WHOLE is a match, however much context came with it. So the other
    direction is measured too and the better of the two wins, which is also what keeps this from turning
    into a rule about dates or filler words: nothing here knows what «Thursday» is, only that the label was
    fully named.
    """
    if not ref_n or not label_n:
        return 0.0
    ratio = difflib.SequenceMatcher(None, ref_n, label_n).ratio()
    return _coverage(ref_n, label_n) * 2.0 + ratio            # token overlap weighs more than the raw ratio


# Result of reference resolution.
class RefResult:
    def __init__(self, ok, payload=None, needs=None, candidates=None):
        self.ok = ok                    # True if resolved (or no resolution was needed)
        self.payload = payload          # payload updated with the real id (if ok)
        self.needs = needs              # 'ref' | 'ambiguous' | 'no_match' when ok=False
        self.candidates = candidates or []   # candidate labels (to ask the operator)


def _qualified(rows: list[dict]) -> list[str]:
    """Candidate labels, each carrying its `hint` when the labels alone do not tell them apart — asking «which
    one: New, New, New?» is not a question.

    EVERY candidate list goes through here, including the ones for `ref` and `no_match` (V2-710): those
    passed the raw labels straight through and he heard «Which one exactly? I have renovar el seguro del
    coche, renovar el seguro del coche, Dentist.» — the same row twice, in a menu of three."""
    labels = [str(i.get("label") or "") for i in rows]
    dup = {x for x in labels if labels.count(x) > 1}
    out: list[str] = []
    for i, label in zip(rows, labels):
        hint = str(i.get("hint") or "").strip()
        # The hint goes ONLY on the rows that actually collide: pinning it to every candidate turns a clean
        # three-name menu into three sentences, and it is doing no work on the names that are already unique.
        if label in dup and hint:
            label = f"{label} ({hint})"
        if label not in out:                # rows identical DOWN TO THE HINT are one question, not two
            out.append(label)
    return out


def resolve(widget_id: str, action: str, ref: str, payload: dict | None = None,
            order: str = "") -> RefResult:
    """Resolve a natural-language reference to the real item id for `action`. Returns a `RefResult`:
    - ok=True + payload (with the real id filled) if resolved, or if the action does not act on an existing item.
    - ok=False with `needs` ('ref'|'ambiguous'|'no_match') and `candidates` so the caller ASKS instead of inventing
      an id. NEVER raises.

    `order` is the OPERATOR'S OWN SENTENCE, and it is the reference of LAST RESORT (V2-708). The model is
    asked to put an existing item in `item`; when it does not, everything needed to find the row is still
    sitting in what he said, and refusing over it is the failure he measured five times in one session —
    «Thursday, seventeenth. Please delete that appointment… A dentist.» answered with a recital of his
    calendar. Last resort on purpose: an explicit `item` still wins, and the sentence is only ever used to
    FIND a row that already exists, never to widen anything (the resolution either names one row or asks).
    ⚠️ Pass HIS half of the turn, never the composed prompt: a `[SISTEMA]` note carries the candidate labels
    themselves, so feeding it in here would make every reference ambiguous.
    """
    payload = dict(payload or {})
    field = id_field_for_action(widget_id, action)
    if not field:
        return RefResult(True, payload)                       # nothing to resolve (e.g. add_meeting)

    idx = [i for i in _ref_index(widget_id) if i.get("field") == field]

    # If the model ALREADY gave an id that really EXISTS, respect it (do not overwrite it).
    given = str(payload.get(field) or "").strip()
    if given and any(i["id"] == given for i in idx):
        return RefResult(True, payload)

    # Text to search for: the model's explicit ref, or —if it did not give one— what it put in the id field (often an
    # invented description/value that sometimes matches by text, e.g. the task title), or his own words.
    named = _norm(ref) or _norm(given)
    query = named or _norm(order)
    # An action the manifest itself calls optional RUNS without a selector («avisos para todas las citas del
    # jueves» is `set_reminder` with a date and no title). It may still be pointed at one row, so it goes
    # through the whole resolution — it just never REFUSES for lack of a name the operator never had to give.
    lenient = selector_is_optional(widget_id, action, field) and not named
    if not named:                                          # …and a sentence dates things — see `_TEMPORAL`
        query = " ".join(t for t in query.split() if t not in _TEMPORAL)
    if not query or not idx:
        if lenient:
            return RefResult(True, payload)
        if not query:
            return RefResult(False, needs="ref", candidates=_qualified(idx)[:6])
        return RefResult(False, needs="no_match")

    exact = [i for i in idx if query == _norm(i["label"])]    # an EXACT title beats any reading of position
    if len(exact) == 1:
        payload[field] = exact[0]["id"]
        return RefResult(True, payload)
    # Same-named rows, and the reference carries the TIME or DATE that tells them apart — «Catch up with Oscar
    # tomorrow September 27 at 16:15» over two «Catch up with Oscar» at 15:30 and 16:15 (demo run, 2026-09-26):
    # it came back ambiguous, and the «27» was about to be read as a row NUMBER. Read from the RAW reference
    # (normalising strips the colon) against the rows' own hints; exactly one match, or nothing changes.
    _toks = set(re.findall(r"\b\d{1,2}:\d{2}\b|\b\d{4}-\d{2}-\d{2}\b", f"{ref or ''} {given}"))
    if _toks:
        _named = [i for i in idx if _norm(i["label"]) and _norm(i["label"]) in query]
        _by_time = [i for i in _named if any(t in str(i.get("hint") or "") for t in _toks)]
        if len(_named) > 1 and len(_by_time) == 1:
            payload[field] = _by_time[0]["id"]
            return RefResult(True, payload)
    # Two rows with the SAME label are two DIFFERENT things, so more than one exact hit falls THROUGH to the
    # scorer, which ties them and makes the tie-break ask. The old code iterated the index and returned the
    # first match: measured on 29 rows all titled «New» that arrived in one day, `cancel_meeting` resolved
    # to one of them with nobody asked. Deliberately not a branch of its own — a second place to decide the
    # same thing is a second place for the two to disagree.

    if positional(widget_id, action):
        # THE PRINTED NUMBER FIRST, when the widget publishes one (V2-747) — a card with several numbered
        # lists cannot be counted flat. `None` means «this index does not number its rows», so every widget
        # that does not keeps the flat reading below, unchanged.
        _num = _numbered_ref(query, idx)
        if _num is not None:
            _rows, _amb = _num
            if _amb:
                return RefResult(False, needs="ambiguous", candidates=_qualified(_rows or idx)[:6])
            payload[field] = _rows[0]["id"]
            return RefResult(True, payload)
        _pos = _position_ref(query, len(idx))
        if _pos is not None:                               # «the first one» / «3» — see `_position_ref`
            payload[field] = idx[_pos]["id"]
            return RefResult(True, payload)

    scored = sorted(((_score(query, _norm(i["label"])), i) for i in idx), key=lambda s: -s[0])
    best_score, best = scored[0]
    second = scored[1][0] if len(scored) > 1 else 0.0
    if best_score < 1.0:
        if lenient:
            return RefResult(True, payload)
        return RefResult(False, needs="no_match", candidates=_qualified(idx)[:6])
    if len(scored) > 1 and (best_score - second) < 0.5:       # tie → do not guess, ask
        close = [i for s, i in scored if best_score - s < 0.5][:4]
        options = _qualified(close)
        # …unless the tied rows are INDISTINGUISHABLE, in which case there is no question to ask and
        # nothing he could answer. Measured (V2-709, session `234457a3`): two identical duplicates of
        # «Cita Agencia Tributaria…», and eight turns of «Which one exactly? I have Cita Agencia
        # Tributaria…» offering ONE option — «delete one of those, I don't care which», «those are the
        # same», «Are you stupid or what?». The door exists so we never act on the WRONG item; when the
        # rows are interchangeable there is no wrong item, so asking is the defect and not the safeguard.
        if len(options) > 1:
            return RefResult(False, needs="ambiguous", candidates=options)
    payload[field] = best["id"]
    return RefResult(True, payload)


def label_for(widget_id: str, field: str, item_id: str) -> str:
    """HUMAN label for widget item `item_id` (`field`) — to compose a readable message (e.g. confirmation text)
    without exposing the internal id. '' if not found. Generic (reads `ref_index`)."""
    iid = str(item_id or "").strip()
    if not iid:
        return ""
    for i in _ref_index(widget_id):
        if i.get("field") == field and str(i.get("id")) == iid:
            return str(i.get("label") or "").strip()
    return ""


_MAX_DIGEST_CHARS = 1800


def prompt_digest(widget_id: str) -> str:
    """REAL content of an OPEN widget, so the brain can REASON about what the operator has in front of them — not just
    name it. OPTIONAL contract in the widget's `data.py`:

        def prompt_digest() -> str:
            '''Text summary of what is inside NOW. Compact: travels in every turn prompt.'''

    Why it exists (2026-08-09): `items_line` only publishes `label (hint)`, so when asked "does the hotel in proposal
    2 have wifi?" —a fact WRITTEN in the card the operator is looking at— the brain did not have it in the prompt:
    it either guessed or escalated a new search to recover something it already had. That is the difference between a
    screen the agent SEES and one it has merely rendered.

    Intentionally bounded (`_MAX_DIGEST_CHARS`): this is a summary for reasoning, not the full record — complete
    detail lives in the widget itself (its detail view), not in every turn prompt. Only requested for OPEN widgets, so
    a large catalog pays nothing for this.
    Best-effort: a broken widget cannot break the turn."""
    try:
        import importlib
        mod = importlib.import_module(f"widgets.{widget_id}.data")
        fn = getattr(mod, "prompt_digest", None)
        if not callable(fn):
            return ""
        out = str(fn() or "").strip()
    except Exception:
        return ""
    if len(out) > _MAX_DIGEST_CHARS:
        out = out[:_MAX_DIGEST_CHARS].rsplit("\n", 1)[0] + "\n… (recortado — el resto está en la propia tarjeta)"
    return out


def items_line(widget_id: str) -> str:
    """Compact line with the widget's LIVE items (label + hint) for the brain brief, so it knows WHAT exists and can
    reference it naturally. No internal ids (the model references by language).

    EMPTY ≠ NO INDEX (fix 2026-08-02): a widget that exposes `ref_index` but has nothing inside SAYS so. Previously it
    returned "" in both cases, so the brain could not distinguish "this card is open and empty" from "this card does
    not publish its items" — and with the results sheet open and blank it answered "here it is" to the operator, who
    saw nothing. An empty widget is a fact the brain must see."""
    if not _exposes_ref_index(widget_id):
        return ""
    idx = _ref_index(widget_id)
    if not idx:
        return ("items ahora: NINGUNO — la tarjeta está ABIERTA pero VACÍA: el operador no ve NADA dentro, así que "
                "no des por entregado lo que hay que poner ahí")
    bits = []
    for i in idx[:12]:
        h = str(i.get("hint") or "").strip()
        bits.append(f"«{i['label']}»" + (f" ({h})" if h else ""))
    return "items ahora: " + " · ".join(bits)
