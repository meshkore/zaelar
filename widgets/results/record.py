#
# record.py — how a FINDING is sanitised before it is allowed onto the sheet (V2-702).
#
# Extracted from `data.py` byte for byte to pay the architecture ratchet (1006 > 991 after V2-702 added `kind`).
# The cut is where the file already had a seam: everything here turns ONE VALUE from a model's payload into
# something the surface can paint — the rating, the photos, the lines, and the closed block vocabulary of a
# dynamic record — and none of it knows anything about sheets, instances, tabs or actions. It is imported back
# and re-exported by `data.py`, which IS the sheet's contract for everyone else, so no caller changed.
#
# The two rules the whole file exists to enforce, both older than this extraction:
#
#   · NOTHING ARBITRARY REACHES THE RENDERER. The payload comes from a worker that read the open web, so the
#     schemas are CLOSED: an unknown block `kind` is dropped rather than degraded to text (a block the operator
#     will not see beats one drawn where it should not be), and `widget.js` paints with textContent only.
#   · EVERY SHAPE AN LLM PLAUSIBLY EMITS IS ACCEPTED. A score arrives as `8.7`, as "8,7/10" or as
#     {value,max,label,why}; facts arrive as a dict, as pairs or as {label,value} objects. Refusing the shape
#     instead of reading it is how a real finding becomes an empty card.
#
from __future__ import annotations

# ── DYNAMIC RECORD: CLOSED block vocabulary ──────────────────────────────────────────────────────────────────
# A different result type needs a different record, and the fixed schema forced everything that did not fit into
# prose. This solves it WITHOUT accepting HTML from the worker: these are composition pieces the surface paints with
# textContent. Any `kind` outside this list is discarded entirely (not degraded to text: a block the operator will not
# see is better than one displayed where it should not be).
_BLOCK_KINDS = ("text", "facts", "chips", "gallery", "meter", "table", "link", "section")
_MAX_BLOCKS = 14         # a record, not a document
_MAX_CHIPS = 14
_MAX_TABLE_ROWS = 24
_MAX_TABLE_COLS = 6
_MAX_CELL_CHARS = 90

_MAX_LINES = 80
_MAX_LINE_CHARS = 300
_MAX_IMAGES = 12         # the detail page's photo gallery
_MAX_FACTS = 30          # label→value sheet (check-in, port, cancellation policy...)
_MAX_FACT_CHARS = 200


#: How many scalar leaves one structured value may lend its slot (V2-831 R9); a slot is a datum, not a dump.
_FLAT_LEAVES = 4


def flat(value) -> str:
    """ONE VALUE → the text a slot paints (V2-831 R9). A network agent sends `rating: {value, count}` and
    `location: {country}`; `str()` of those painted Python on the card. By SHAPE, never by field name: a scalar is its
    text, a dict or a list lends its scalar leaves (two levels deep, distinct, at most four) joined by « · », and a
    bool, None or an unknown object lends nothing — a slot that cannot be read is dropped, never repr'd."""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "" if _num(value) is None else str(_num(value))
    leaves: list[str] = []

    def walk(v, depth: int) -> None:
        seq = v.values() if isinstance(v, dict) else v if isinstance(v, (list, tuple)) else None
        if seq is None:
            s = flat(v).strip() if isinstance(v, (str, int, float)) and not isinstance(v, bool) else ""
            if s and s not in leaves and len(leaves) < _FLAT_LEAVES:
                leaves.append(s)
        elif depth < 2:
            for x in seq:
                walk(x, depth + 1)
    walk(value, 0)
    return " · ".join(leaves)


def _clean_facts(raw) -> list[dict]:
    """`facts` is the STRUCTURED half of a result — the part the operator asks precise questions about later
    ("what time is check-in?", "does it include breakfast?"). Written naturally as {label: value} by whoever found it,
    but STORED as an ordered list so the order the researcher chose survives the round-trip (and so a label can
    repeat, which a dict silently swallows). A list of pairs or of {label,value} dicts is accepted too — the
    payload comes from an LLM and all three shapes are things it plausibly emits."""
    out: list[dict] = []
    items = []
    if isinstance(raw, dict):
        items = list(raw.items())
    elif isinstance(raw, (list, tuple)):
        for entry in raw:
            if isinstance(entry, dict):
                items.append((entry.get("label") or entry.get("k") or entry.get("name"),
                              entry.get("value") if entry.get("value") is not None else entry.get("v")))
            elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
                items.append((entry[0], entry[1]))
    for label, value in ((flat(k).strip(), flat(v).strip()) for k, v in items):
        if not label or not value:
            continue
        out.append({"label": label[:80], "value": value[:_MAX_FACT_CHARS]})
        if len(out) >= _MAX_FACTS:
            break
    return out


_MAX_META = 4


def _clean_meta(raw) -> list[dict]:
    """`meta` — the 1-4 SHORT chips a list card shows under its title (V2-797): the data that decides at a glance
    (a distance, opening hours, a rating). A bare string is a chip with no label; a label/value pair (any of the
    `facts` shapes) keeps its label. Bounded: a chip is a chip, not a paragraph."""
    out: list[dict] = []
    seq = list(raw.items()) if isinstance(raw, dict) else list(raw) if isinstance(raw, (list, tuple)) else []
    for entry in seq:
        if not isinstance(entry, (dict, list, tuple)):
            chip = {"value": flat(entry).strip()[:60]}
        else:
            f = _clean_facts([entry] if not isinstance(entry, dict) or "label" in entry or "k" in entry
                             or "name" in entry else entry)
            chip = {"label": f[0]["label"][:30], "value": f[0]["value"][:60]} if f else {}
        if chip.get("value"):
            out.append(chip)
        if len(out) >= _MAX_META:
            break
    return out


def _clean_lines(raw, cap: int) -> list[str]:
    seq = raw if isinstance(raw, (list, tuple)) else [raw]
    return [t[:_MAX_LINE_CHARS] for t in map(flat, seq) if t.strip()][:cap]


def _clean_images(raw) -> list[str]:
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return []
    return [str(x)[:500] for x in raw if x not in (None, "")][:_MAX_IMAGES]


def _num(raw, default=None):
    if isinstance(raw, bool) or raw in (None, ""):
        return default
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return default
    if v != v or v in (float("inf"), float("-inf")):     # NaN/inf: a number that cannot be painted or compared
        return default
    return int(v) if float(v).is_integer() else round(v, 2)


def _clean_score(raw) -> dict | None:
    """THE RATING. The operator explicitly requested it in the detail record, and it had been in the schema for
    months WITHOUT being rendered anywhere — it was saved and lost.

    Accept as a bare number (`8.7`), text ("8.7/10"), or object `{value,max,label,why}`. `why` is what makes it truly
    useful: a score without its reason cannot be discussed or corrected."""
    if raw in (None, ""):
        return None
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        v = _num(raw)
        return None if v is None else {"value": v, "max": 10 if v <= 10 else 100}
    if isinstance(raw, str):
        s = raw.strip()[:60]
        if not s:
            return None
        body, _, mx = s.partition("/")
        v = _num(body.replace(",", "."))
        if v is None:
            return {"label": s}                          # "Excellent", "A+": valid as a label, not as a number
        out = {"value": v, "max": _num(mx) or (10 if v <= 10 else 100)}
        return out
    if isinstance(raw, dict):
        out: dict = {}
        v = _num(raw.get("value") if raw.get("value") is not None else raw.get("score"))
        if v is not None:
            out["value"] = v
            out["max"] = _num(raw.get("max")) or (10 if v <= 10 else 100)
        for k in ("label", "why"):
            if raw.get(k):
                out[k] = str(raw[k])[:_MAX_FACT_CHARS]
        return out or None
    return None


def _clean_block(raw, depth: int = 0) -> dict | None:
    """ONE block in a dynamic record. Closed vocabulary: an unknown `kind` is not degraded to text, it is dropped."""
    if not isinstance(raw, dict):
        return None
    kind = str(raw.get("kind") or "").strip().lower()
    if kind not in _BLOCK_KINDS:
        return None
    b: dict = {"kind": kind}
    if raw.get("title"):
        b["title"] = str(raw["title"])[:120]

    if kind == "text":
        lines = _clean_lines(raw.get("lines") if raw.get("lines") is not None else raw.get("text"), _MAX_LINES)
        if not lines:
            return None
        b["lines"] = lines
        if str(raw.get("tone") or "").lower() in ("muted", "strong", "warn"):
            b["tone"] = str(raw["tone"]).lower()
    elif kind == "facts":
        f = _clean_facts(raw.get("facts") if raw.get("facts") is not None else raw.get("items"))
        if not f:
            return None
        b["facts"] = f
    elif kind == "chips":
        src = raw.get("chips") if raw.get("chips") is not None else raw.get("items")
        chips = [str(c)[:60] for c in src if c not in (None, "")][:_MAX_CHIPS] if isinstance(src, (list, tuple)) else []
        if not chips:
            return None
        b["chips"] = chips
    elif kind == "gallery":
        img = _clean_images(raw.get("images") if raw.get("images") is not None else raw.get("items"))
        if not img:
            return None
        b["images"] = img
    elif kind == "meter":
        v = _num(raw.get("value"))
        if v is None:
            return None
        b["value"] = v
        b["max"] = _num(raw.get("max")) or (10 if v <= 10 else 100)
        if raw.get("caption"):
            b["caption"] = str(raw["caption"])[:_MAX_FACT_CHARS]
    elif kind == "table":
        rows_raw = raw.get("rows")
        if not isinstance(rows_raw, (list, tuple)):
            return None
        cols = [str(c)[:40] for c in raw.get("columns") or [] if c not in (None, "")][:_MAX_TABLE_COLS]
        rows = []
        for r in rows_raw:
            if not isinstance(r, (list, tuple)):
                continue
            cells = [("" if c is None else str(c))[:_MAX_CELL_CHARS] for c in r][:_MAX_TABLE_COLS or 6]
            if any(c for c in cells):
                rows.append(cells)
            if len(rows) >= _MAX_TABLE_ROWS:
                break
        if not rows:
            return None
        if cols:
            b["columns"] = cols
        b["rows"] = rows
    elif kind == "link":
        url = str(raw.get("url") or "").strip()[:500]
        if not url:
            return None
        b["url"] = url
        b["label"] = str(raw.get("label") or url)[:120]
    elif kind == "section":
        if depth:                                        # ONE nesting level: a record, not a tree
            return None
        inner = _clean_blocks(raw.get("blocks"), depth + 1)
        if not inner:
            return None
        b["blocks"] = inner
    return b


def _clean_blocks(raw, depth: int = 0) -> list[dict]:
    blocks = (_clean_block(r, depth) for r in raw) if isinstance(raw, (list, tuple)) else ()
    return [b for b in blocks if b][:_MAX_BLOCKS]
