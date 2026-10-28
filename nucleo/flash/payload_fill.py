"""What the operator's own words fill into an action's payload (V2-778 F1, 2026-10-01).

Moved out of `nucleo/flash/direct_action.py` (989 lines, over the 900 a new file may reach): the readers that
decide which declared key a value fills (`fillable_key`), and the fills themselves — a number he said
(`number_fill`), an enum value (`enum_fill`), a person (`person_fill`) — composed by `fill_missing`. Unchanged;
`direct_action` imports every name back. They only ADD a key that is absent, from a declared alias or a spoken
number (V2-756).
"""
from __future__ import annotations



#: The declared marker for «this payload key may be left out». Both spellings, because the manifests
#: are product data and carry the operator's language as well as the engine's.
_OPTIONAL_MARKS = ("(opcional)", "(optional)")


#: How a manifest spells «this key takes ONE OF THESE», e.g. `"tab": "inicio | player | cola"` or
#: `"by": "'title' o 'added'"`. A key like that is a CHOICE, and a sentence is not one of its values.
#: Found while declaring `youtube:show_tab` (V2-742): its payload is an enumeration, and without this
#: the rung would have filled it with «vuelve al catálogo de vídeos» and the widget would have
#: refused an order the operator had given perfectly well.
_ENUM_MARKS = (" | ", "' o '", "' or '", '" o "', '" or "')


def _optional(desc) -> bool:
    d = str(desc or "").lower()
    return any(m in d for m in _OPTIONAL_MARKS)


def _base_of(widget_id: str) -> str:
    from nucleo.flash import turn_brief as _tb
    return _tb._base_of(widget_id)


def fillable_key(widget_id: str, action: str) -> str:
    """The ONE payload key that words may fill for this action, or "" when there is not exactly one.

    «Exactly one» is the whole rule and it is deliberately strict: two required keys mean the action
    needs a DATUM we do not have, and that is a question to ask (V2-712's ASK_FACT), not a call to
    make. Zero required keys is fine and returns "" too — the caller fires with an empty payload,
    which is what a no-argument action wants.
    """
    try:
        from nucleo.flash import frontend as _fe
        from widgets import refs as _refs
        base = _base_of(widget_id)
        spec = (_fe.declared_actions(base) or {}).get(action) or {}
        payload = spec.get("payload") if isinstance(spec, dict) else None
        if not isinstance(payload, dict):
            return ""
        required = [k for k, v in payload.items() if not _optional(v)]
        if len(required) != 1:
            return ""
        key = str(required[0])
        # A key that names an item ALREADY ON the card is a selector, not a query: filling it with a
        # sentence would ask the widget to play a row that does not exist.
        # …unless the widget publishes no row index and matches the reference ITSELF (a passage in a document):
        # there his words ARE the reference (refs.resolve's own rule — demo pass 2026-09-28, F2).
        if (_refs.id_field_for_action(base, action) or "") == key and _refs._exposes_ref_index(base):
            return ""
        # Nor is a sentence one of an enumeration's values (V2-742).
        if any(m in str(payload.get(key) or "") for m in _ENUM_MARKS):
            return ""
        # Nor a list of RECORDS (`{url, title, …}`): a sentence is never one. `show-real-photo-of-a-new-car__es`
        # (2026-10-14): the verdict backstop filled `imagenes:show {items: «¿Cómo que no has podido?…»}`.
        if "{" in str(payload.get(key) or ""):
            return ""
        return key
    except Exception:  # noqa: BLE001
        return ""


def _payload_spec(widget_id: str, action: str) -> dict:
    try:
        from nucleo.flash import frontend as _fe
        spec = (_fe.declared_actions(_base_of(widget_id)) or {}).get(action) or {}
        payload = spec.get("payload") if isinstance(spec, dict) else None
        return payload if isinstance(payload, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def enum_fill(widget_id: str, action: str, words: str) -> dict:
    """`{key: value}` when the action's ONE required key is a declared choice and the operator's words
    name exactly one of its values or aliases; `{}` otherwise. See `widgets.enums`."""
    try:
        from widgets import enums as _enums
        payload = _payload_spec(widget_id, action)
        required = [k for k, v in payload.items() if not _optional(v)]
        if len(required) != 1:
            return {}
        key = str(required[0])
        value = _enums.resolve(str(payload.get(key) or ""), "", words)
        return {key: value} if value else {}
    except Exception:  # noqa: BLE001
        return {}


#: Spoken numbers reach us as words — Deepgram writes «el vídeo número tres» / «number five», never «3». The
#: words are the ONE closed class `widgets/refs.number_words()` keeps for every language pack we speak.
def _spell(m) -> str:
    import unicodedata as _ud
    from widgets import refs as _refs
    w = "".join(c for c in _ud.normalize("NFKD", m.group(0).lower()) if not _ud.combining(c))
    return str(_refs.number_words().get(w, m.group(0)))


def _word_numbers_re():
    import re as _re
    from widgets import refs as _refs
    return _re.compile("|".join(r"\b%s\b" % w for w in sorted(_refs.number_words(), key=len, reverse=True)),
                       _re.IGNORECASE)


_WORD_NUMBERS = _word_numbers_re()


def number_fill(widget_id: str, action: str, words: str) -> dict:
    """`{key: n}` when the action's ONE fillable key is a 1-based INDEX and he said exactly one number.

    The sibling of `enum_fill` and the same rule: a value he SAID is read, never invented (V2-741).
    «Ahora quiero que me pongas el vídeo número tres» over a band of six is a 3. Two different numbers,
    or none, is not a fill — it is a question to ask.
    """
    try:
        import re as _re
        key = fillable_key(widget_id, action)
        if not key:
            return {}
        spec = str(_payload_spec(widget_id, action).get(key) or "").lower()
        if not any(m in spec for m in ("1-based", "1-n", "número del resultado", "numero del resultado")):
            return {}
        nums = [int(_spell(m)) for m in _WORD_NUMBERS.finditer(words or "")]       # a SPOKEN number counts
        # …a DIGIT only when it is marked as one («number 3», «nº 3», «el 6», «#3») or is all he said: «Apolo 11»
        # is a title, not row eleven.
        nums += [int(x) for x in _re.findall(r"(?:\b(?:number|n[uú]mero|n[º°o]\.?|el|la|the)\s*|#)(\d{1,2})\b",
                                                words or "", _re.IGNORECASE)]
        if _re.fullmatch(r"\s*(\d{1,2})\s*[.!]?\s*", words or ""):
            nums.append(int(_re.sub(r"\D", "", words)))
        nums = [n for n in nums if 1 <= n <= 99]
        return {key: nums[0]} if len(set(nums)) == 1 else {}
    except Exception:  # noqa: BLE001
        return {}


def _row_labels(card: str) -> list[tuple[str, str]]:
    """`(title, price)` of every row the card shows now, in its own order (1-based index = position + 1)."""
    try:
        from nucleo import truth as _truth
        view = _truth.widget_view(card) or {}
    except Exception:  # noqa: BLE001
        return []
    rows = view.get("items") if isinstance(view, dict) else None
    out = []
    for r in rows if isinstance(rows, list) else []:
        if isinstance(r, dict):
            out.append((str(r.get("title") or r.get("name") or "").strip(), str(r.get("price") or "").strip()))
    return out


def row_named_fill(widget_id: str, action: str, card: str, model_words: str) -> dict:
    """`{key: n}` when the MODEL's own words name exactly one row of the card, and the action's one fillable key is a
    1-based INDEX.

    Demo pass 80 (2026-10-03), S3 «open the one that's the best deal»: the model called nothing and SAID «the Samsung
    ViewFinity S7's ficha is open … at $189.99»; the verdict completed `results:detail`, but the only words it had
    to fill `index` with were the operator's sentence — rejected, and the screen never moved under a reply saying it
    had. The model had already read the sheet and named the row: that is a reading, not an invention, the same rule
    as `number_fill` (a number he SAID). A row counts as named when its PRICE appears in the words, or when at least
    two of its distinctive title words do; two rows tied is a question, never a pick."""
    import re as _re
    try:
        key = fillable_key(widget_id, action)
        if not key or not (model_words or "").strip():
            return {}
        spec = str(_payload_spec(widget_id, action).get(key) or "").lower()
        if not (any(m in spec for m in ("1-based", "1-n", "número del resultado", "numero del resultado"))
                or _re.fullmatch(r"\d+", spec.strip())):
            return {}
        said = (model_words or "").lower()
        said_toks = set(_re.findall(r"[a-z0-9]+", said))
        scores = []
        for title, price in _row_labels(card):
            toks = [t for t in _re.findall(r"[a-z0-9]+", title.lower()) if len(t) > 2 and not t.isdigit()]
            hits = sum(1 for t in dict.fromkeys(toks) if t in said_toks)
            digits = _re.sub(r"[^0-9.]", "", price)
            priced = bool(digits) and digits.rstrip(".") in _re.sub(r"[^0-9. ]", " ", said).split()
            scores.append((2 if priced else 0) + hits)
        if not scores:
            return {}
        best = max(scores)
        if best < 2 or scores.count(best) != 1:
            return {}
        return {key: scores.index(best) + 1}
    except Exception:  # noqa: BLE001
        return {}


def person_fill(widget_id: str, action: str, payload: dict, words: str) -> dict:
    """`{"contact": <name>}` when the action declares a `contact`, the call left it empty and his sentence names
    exactly ONE person of the directory; `{}` otherwise — two named, or none, is the model's to ask.

    Demo pass 2026-09-28 (full18 E3): «send the invoice to quinn…» — the model called `reply` (to the invoice's
    SENDER), the outward-act gate rightly ran the verdict's `forward` instead, with the reply's payload: no
    recipient, and the forward was refused. The recipient was in his sentence; the directory knows who that is."""
    try:
        if "contact" not in _payload_spec(widget_id, action) or str((payload or {}).get("contact") or "").strip():
            return {}
        from widgets.contactos import data as _ct
        named = _ct.people_named(words or "")
        return {"contact": str(named[0].get("name") or "")} if len(named) == 1 and named[0].get("name") else {}
    except Exception:  # noqa: BLE001
        return {}


def fill_missing(widget_id: str, action: str, payload: dict, words: str) -> dict:
    """What the MODEL's own call left out and his words can supply honestly, or `{}`.

    V2-756. «Pausa el vídeo. Vuelve al catálogo.» → the model called `widget_data(youtube, show_tab)`
    with an EMPTY payload and the widget answered `unknown_tab`: a correct order, the correct action,
    refused over one missing key whose value was sitting in his sentence («al catálogo» is `inicio`,
    declared right there in the manifest). He asked «¿Has ignorado la orden que te he dado?».

    Only ever ADDS a key the call left empty, and only from the two readings that are not inventions:
    a declared ALIAS of an enumerated value (V2-754) or a number he said. A call that already carries
    its key is untouched — this repairs an omission, it never edits a decision.
    """
    try:
        if (who := person_fill(widget_id, action, payload, words)):
            return who
        spec = _payload_spec(widget_id, action)
        required = [k for k, v in spec.items() if not _optional(v)]
        if len(required) != 1:                       # zero or several: nothing single to repair
            return {}
        if str((payload or {}).get(required[0]) or "").strip():
            return {}                                # the call carries its key — not this function's business
        return enum_fill(widget_id, action, words) or number_fill(widget_id, action, words)
    except Exception:  # noqa: BLE001
        return {}


#: Which side of the other row he put it on. A closed class of position words, not a verb table: the verdict has
#: already named the action (`move`), so this only reads WHERE, the way `refs._ORDINALS` reads «the third».
_AFTER_WORDS = frozenset("after behind below under despues detras tras debajo".split())
_BEFORE_WORDS = frozenset("before ahead above antes delante encima".split())
#: Cardinals that are also articles («una», «un») are no row reference inside a sentence.
_NOT_A_ROW_NUMBER = frozenset({"un", "uno", "una"})


def _row_mentions(words: str, rows: list[dict], base: str = "") -> list[tuple[int, int]]:
    """`(offset, row_id)` of every row the words NAME, in the order they are named.

    A row is named by a spoken position («the third», «el segundo»), a marked digit («number 3»), or a word of its
    title that no OTHER row carries («the skills one» over one title with «Skills»). A word every row shares
    («Maradona» over a queue of Maradona videos) names nothing. A row he named and TOOK BACK («the last… no, the second
    to last») is not one of them: the turn's brief says which (`brief_screen.item_ref_question`), never a word table."""
    import re as _re
    from widgets import refs as _refs
    norm = _refs.from_the_end(_refs._norm(words or ""))
    toks = [(m.start(), m.group(0)) for m in _re.finditer(r"[a-z0-9ñ]+", norm)]
    n = len(rows)
    nums = _refs.number_words()
    out = [(off, i + 1) for off, t in toks if (i := _refs.from_end_index(t, n)) is not None]    # «el penúltimo»
    for off, t in toks:
        if t in nums and t not in _NOT_A_ROW_NUMBER and 1 <= nums[t] <= n:
            out.append((off, nums[t]))
    for m in _re.finditer(r"(?:\b(?:number|numero|n[o]|el|la|the)\s*|#)(\d{1,2})\b", norm):
        if 1 <= int(m.group(1)) <= n:
            out.append((m.start(1), int(m.group(1))))
    title_toks = [set(t for t in _refs._norm(r.get("label")).split() if len(t) > 3 and not t.isdigit()) for r in rows]
    for i, own in enumerate(title_toks):
        unique = own.difference(*(o for j, o in enumerate(title_toks) if j != i))
        hits = [off for off, t in toks if t in unique]
        if hits:
            out.append((min(hits), i + 1))
    first: dict[int, int] = {}
    for off, rid in sorted(out):
        first.setdefault(rid, off)
    from nucleo.turn import brief as _brief
    gone = _brief.withdrawn_rows(_brief.of_this_turn(), base) if base else set()
    return sorted((off, rid) for rid, off in first.items() if str(rows[rid - 1]["id"]) not in gone)


def reorder_fill(widget_id: str, action: str, words: str, model_words: str = "") -> dict:
    """`{item: n, before|after: m}` when the action declares a row to move beside ANOTHER row and the words name
    exactly two rows with the side between them; `{}` otherwise.

    The video-queue use case (2026-10-11): «the third one before the second» — the verdict read `youtube:move` at
    1.00, the model called nothing and said «Done — Most Creative is now ahead of Los Goles», and `resolve` could not
    fill a move (two keys), so the queue kept its order under a claim. The rows he named are a reading, not an invention
    (the `number_fill` rule); his words first, then the model's own claim, which names the same two rows."""
    try:
        from widgets import refs as _refs
        spec = _payload_spec(widget_id, action)
        field = _refs.id_field_for_action(_base_of(widget_id), action) or ""
        if not field or field not in spec or not ({"before", "after"} & set(spec)):
            return {}
        rows = [r for r in _refs._ref_index(_base_of(widget_id)) if r.get("field") == field]
        if len(rows) < 2:
            return {}
        for text in (words, model_words):
            named = _row_mentions(text, rows, _base_of(widget_id))
            if len(named) != 2:
                continue
            (a_off, a_row), (b_off, b_row) = named
            between = set(_refs.from_the_end(_refs._norm(text))[a_off:b_off].split())   # the offsets' own text
            side = "after" if between & _AFTER_WORDS else ("before" if between & _BEFORE_WORDS else "")
            if side and side in spec:
                return {field: str(rows[a_row - 1]["id"]), side: str(rows[b_row - 1]["id"])}
        return {}
    except Exception:  # noqa: BLE001
        return {}


def choice_or_order_fill(widget_id: str, action: str, words: str, model_words: str = "") -> tuple[dict, str]:
    """`(payload, source)` for an action no single query key fills: a declared CHOICE he named (`enum-alias`), else
    two rows he put in order (`said-order`); `({}, "")` when neither."""
    if (filled := enum_fill(widget_id, action, words)):
        return filled, "enum-alias"
    if (filled := reorder_fill(widget_id, action, words, model_words)):
        return filled, "said-order"
    from nucleo.flash import move_fill as _mf     # «the one playing, first» / a slot answering the card's question
    if (filled := _mf.move_fill(widget_id, action, words, model_words)):
        return filled, "said-move"
    return {}, ""


def named_row(widget_id: str, action: str, words: str) -> dict:
    """The selector of the ONE row of the card his sentence names (`refs.resolve`'s last-resort reading, V2-708) —
    a reading of what exists, never his sentence stuffed into a selector. agenda-everyday-edits ES (2026-10-15):
    «Ábreme la ficha del dentista» → verdict `agenda:open_meeting` 0.99, the model only said «Voy a abrirla», and
    the rung refused because `title` names a row; the row was right there. None named, or several → {}."""
    try:
        from widgets import refs as _refs
        base = _base_of(widget_id)
        field = _refs.id_field_for_action(base, action)
        # Only a card that PUBLISHES its rows can be read this way: elsewhere `resolve` hands the raw sentence
        # back as the value (demo pass 134, E3: `mensajeria:forward {from: «send the invoice to quinn…»}` — a
        # forward with no recipient and no note, which then asked). A value that is his sentence is not a row.
        if not str(words or "").strip() or not field or not _refs._exposes_ref_index(base):
            return {}
        rr = _refs.resolve(base, action, "", {}, order=words)
        got = dict(rr.payload) if rr.ok and isinstance(rr.payload, dict) else {}
        return got if got.get(field) and str(got.get(field)).strip() != str(words).strip() else {}
    except Exception:  # noqa: BLE001
        return {}
