"""`{item: n, to: m}` for a move whose two halves his words carry — the row that is PLAYING, a slot he named — or
whose other half is the parked refusal of the turn before.

Video-queue use case, ES round of 2026-10-11 (engine 3.36+d6f4a99f): «El que está sonando ahora, ese ponlo el
primero» — `youtube:move` 0.97, and no reading could fill it: `reorder_fill` wants two rows («X before Y»),
`number_fill` wants one bare index. «The one playing» is a row the card itself marks (`ref_index`'s hint), and
«el primero» / «first» / «al principio» is a slot, not a row; the same closed classes `widgets/refs` already reads.
Then «A la 1, ponlo el primero de todos»: a slot alone, answering the card's own question — the item was in the
refused call (`parked_refusal`). Both are readings of what he said, never a guess (the `number_fill` rule):
one slot, one row, or nothing.
"""
from __future__ import annotations

import re

from loguru import logger

#: The row that is playing, said of a row in a sentence. `now`/`actual` stay out («ahora mismo» is about time).
_PLAYING = re.compile(r"\b(?:que (?:esta |se esta )?(?:sonando|reproduciendo)|sonando|suena|reproduciendo|"
                      r"(?:that'?s |that is |is )?playing|now playing|current one|en el reproductor)\b")
#: How a row's hint marks it as playing (`widgets/youtube/data.ref_index`, both product languages).
_PLAYING_HINT = re.compile(r"\b(?:suena|sonando|playing)\b")
_HEAD = "primer[oa]?|first|principio|inicio|top|front|beginning|start|arriba"
_TAIL = "ultim[oa]|last|final|end|bottom|back"
#: «number 3» right after the verb is the ROW («move number 3 to position 2»), so that word stays out of this lead.
_LEAD = (r"(?:a\s+la\s+|al\s+|a\s+|to\s+the\s+|to\s+|at\s+the\s+|at\s+|in\s+|into\s+|en\s+(?:la\s+|el\s+)?|de\s+|"
         r"la\s+|el\s+|the\s+)?(?:posicion\s+|position\s+|puesto\s+|slot\s+|spot\s+|lugar\s+)?")
#: A SLOT said as a destination: after a put/move verb («ponlo el primero», «move it to 3», «put it first»), after a
#: destination preposition («a la 1», «al final», «to the top», «at position 2»), or closing the clause («…primero de
#: todos.», «…first.»). A preposition is the surest marker: when one is said, the others are not read («move 3 to 2»).
_DEST_RES = (
    re.compile(r"\b(?:pon\w*|ponme\w*|mueve\w*|muev\w*|coloca\w*|move|put|place|bump|stick|send)\b"
               r"(?:\s+(?:lo|la|le|me|it|that|this|ese|esa|eso|one))*\s+" + _LEAD +
               r"(?:(\d{1,2})|(" + _HEAD + r")|(" + _TAIL + r"))\b"),
    re.compile(r"\b(?:a\s+la|al|hasta\s+(?:la|el)|to(?:\s+the)?|at(?:\s+the)?|into(?:\s+the)?|en\s+(?:la\s+)?posicion|"
               r"position|posicion|puesto|spot)\s+(?:posicion\s+|position\s+|numero\s+|number\s+)?"
               r"(?:(\d{1,2})|(" + _HEAD + r")|(" + _TAIL + r"))\b"),
    re.compile(r"\b(?:de\s+|the\s+|el\s+|la\s+)?(?:(\d{1,2})|(" + _HEAD + r")|(" + _TAIL + r"))"
               r"(?:\s+(?:de\s+todos|of\s+all|de\s+la\s+(?:cola|lista)|in\s+the\s+(?:queue|list)))?\s*(?:[.,;!]|$)"),
)
_VERB = re.compile(r"\b(?:pon\w*|ponme\w*|mueve\w*|muev\w*|coloca\w*|sube\w*|baja\w*|move|put|place|bump|stick|send)\b")


def _fold(text: str) -> str:
    """Lower-case ASCII with the clause punctuation KEPT: «first, no, last» is two clauses, not one."""
    import unicodedata as _ud
    s = "".join(c for c in _ud.normalize("NFKD", str(text or "")) if not _ud.combining(c)).lower()
    return re.sub(r"[^a-z0-9ñ .,;!?]+", " ", s)


def _destinations(norm: str, n: int) -> tuple[set[int], list[tuple[int, int]]]:
    """`(slots, spans)`: the 1-based slots said as a destination — the preposition-marked ones when any, else the
    rest — and the `(start, end)` of EVERY destination phrase, so none of them is read again as a row."""
    by_rx: list[list[tuple[int, int, int]]] = []
    for k, rx in enumerate(_DEST_RES):
        found: list[tuple[int, int, int]] = []
        if k != 2 or _VERB.search(norm):             # a clause-final ordinal is a destination only under a verb
            for m in rx.finditer(norm):
                digit, head = m.group(1), m.group(2)
                s = int(digit) if digit else (1 if head else n)
                if 1 <= s <= n:
                    found.append((m.start(1 if digit else 2 if head else 3), m.end(), s))
        by_rx.append(found)
    chosen = by_rx[1] if by_rx[1] else by_rx[0] + by_rx[2]
    return {s for _a, _b, s in chosen}, [(a, b) for part in by_rx for a, b, _s in part]


def _playing_row(rows: list[dict]) -> str:
    hits = [str(r.get("id")) for r in rows if _PLAYING_HINT.search(str(r.get("hint") or "").lower())]
    return hits[0] if len(hits) == 1 else ""


def move_fill(widget_id: str, action: str, words: str, model_words: str = "") -> dict:
    """`{item: id, to: slot}` for a move his words — or his words plus the parked refusal — fill; `{}` otherwise."""
    try:
        from nucleo.flash import parked_refusal as _parked
        from nucleo.flash import payload_fill as _pf
        from widgets import refs as _refs
        base = _pf._base_of(widget_id)
        spec = _pf._payload_spec(widget_id, action)
        field = _refs.id_field_for_action(base, action) or ""
        if not field or field not in spec or "to" not in spec:
            return {}
        rows = [r for r in _refs._ref_index(base) if r.get("field") == field]
        n = len(rows)
        if n < 2:
            return {}
        norm = _fold(words)
        slots, spans = _destinations(norm, n)
        to = slots.pop() if len(slots) == 1 else None
        masked = list(norm)
        for a, b in spans:
            masked[a:b] = " " * (b - a)
        rest = "".join(masked)
        item = _playing_row(rows) if _PLAYING.search(rest) else ""
        if not item:
            named = _pf._row_mentions(rest, rows)
            item = str(rows[named[0][1] - 1]["id"]) if len(named) == 1 else ""
        if item and to is not None:
            return {field: item, "to": to}
        if not item and to is None:
            return {}
        parked = _parked.last(base, action)
        if not parked:
            return {}
        prev = parked.get("payload") or {}
        if to is None:
            raw = next((prev.get(k) for k in ("to", "position") if str(prev.get(k) or "").strip()), None)
            if raw is None:
                return {}
            return {field: item, "to": raw}
        prev_item = str(prev.get(field) or "").strip()
        return {field: prev_item, "to": to} if prev_item else {}
    except Exception as e:  # noqa: BLE001
        logger.debug(f"move_fill: skipped — {type(e).__name__}: {e}")
        return {}
