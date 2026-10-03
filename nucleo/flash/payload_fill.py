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
