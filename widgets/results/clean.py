"""widgets/results/clean.py — how a pushed payload becomes the sheet's closed schema: the fields an item,
a part, a source, a rejected row, the summary and the criteria may carry, their caps, and the word-boundary clip.

Moved byte for byte out of `widgets/results/data.py` (refactor2710-12); `data` re-exports every name, so callers
and tests keep saying `data._clean_item` / `data._MAX_ITEMS`.
"""
from .record import (  # noqa: F401
    _MAX_LINES, _clean_blocks, _clean_facts, _clean_images, _clean_lines, _clean_meta, _clean_score, _num)
from .sheet_names import WIDGET_ID


# Fields an item may carry. Anything else pushed is dropped — the payload comes from a worker that read the open
# web, so we never let arbitrary keys through to the renderer (widget.js paints with textContent only, but the
# schema is the contract and it stays closed).
_ITEM_FIELDS = ("title", "subtitle", "price", "badge", "url", "image", "primary", "lines",
                "parts", "images", "facts", "score", "blocks", "full_title", "meta")
#: `full_title` — the title as the listing wrote it, kept when the card's slot clips it. «Premium 3-Seat Sofa –
#: Excellent Condition – Only 6 Months Used» became «Premium 3-Seat Sofa – Excellent…» and the condition it carried
#: was gone from every later turn (2026-10-14): the card paints `title`; a reader of the row reads both.
# A PART is one piece of a composite item (the hotel inside a holiday plan, the ferry, the restaurant). Same
# closed-schema discipline; `kind` is the piece's role ("Hotel", "Ferry", "Restaurante") so the card can label it.
_PART_FIELDS = ("kind", "title", "subtitle", "price", "url", "image", "lines", "facts")

_MAX_ITEMS = 60          # a report the operator can actually read; widget.js renders the first 24 and says how many more
# `lines` used to cap at 4 — fine for a spec-sheet bullet list, but a real request ("show me the lyrics to X") needs
# a whole song's worth of text in ONE item's body (2026-08-03). Raised so a full block of text fits; still bounded
# so a worker can't paste an entire scraped page into a card.
_MAX_PARTS = 6           # a plan is a handful of pieces (hotel+ferry+restaurant), never a list in disguise
_MAX_PART_LINES = 20
# A SOURCE is a website/origin that was attempted, with what HAPPENED there. Status is a closed vocabulary because
# color depends on it and, above all, reading does: "could not enter" and "entered but was capped at 50" are VERY
# different outcomes, yet until today both counted as "nothing".
_SOURCE_FIELDS = ("name", "url", "status", "detail", "found")
_SOURCE_STATUS = ("ok", "partial", "auth", "blocked", "error", "pending")
_MAX_SOURCES = 40
_MAX_DETAIL_CHARS = 200

# SUMMARY: global state + counts + what has been done. `explored`/`selected`/`discarded` are REPORTED by whoever is
# working (only they know how many candidates were truly looked at); what can be derived is derived and labeled as
# derived, never confused (see `_counts`).
_SUMMARY_NUMS = ("explored", "selected", "discarded", "round")

# THE ONES THAT DID NOT MAKE IT, by name (V2-728). Operator, 2026-09-20: *«me encuentra los 5 mejores y
# otros 50 que ha descartado, pues todo eso tiene que quedar vinculado»*. Until now `discarded` was a COUNT
# and nothing else, so «¿por qué no este?» and «enséñame los que tiraste» had no answer anywhere in the
# system — the work had been done and thrown away. A rejection is worth keeping precisely when it is
# ARGUED: the row is (what it was, where, why it lost), and a row with no `why` is not stored, because a
# list of names with no reasons is not an audit, it is a longer list.
#
# Capped well above the kept list on purpose: discarding is most of the work, and the cap exists to bound
# the sheet on disk, not to express an opinion about how much looking is enough.
_REJECTED_FIELDS = ("title", "url", "why", "source")
_MAX_REJECTED = 120
_MAX_WHY_CHARS = 180
_SUMMARY_TEXT = ("state", "note")
_MAX_STEPS = 24          # logbook of what was done: milestones, not every click
_MAX_STEP_CHARS = 160

# CRITERIA used to execute the task. Same names as the `nucleo/research.py` brief (seeded from there) + `changes`:
# corrections the operator gives WHILE searching, which are exactly what used to get lost in conversation.
_CRIT_LISTS = ("hard", "soft", "assumed", "enrichments", "quality_bar", "changes")
_MAX_CRIT = 14
_MAX_CRIT_CHARS = 220


# ── PRESENTATION QUALITY CONTROL (2026-08-10) ────────────────────────────────────────────────────────────────
# Field budgets and rules live in `widgets/presentation.py` (shared by EVERY blank surface); they are only applied
# here. Two things change compared with before:
#   · clipping happens on WORD boundaries and is marked. The old `[:200]` cut a real worker warning
#     ("⚠️ Llevar tu cadena...") into "⚠️ Llevar tu c": an amputated caveat misleads more than its absence.
#   · a payload that breaks the card leaves a TRACE. A prompt is a request, not a guarantee: if a title contains
#     three ideas, it is logged and returned in the action response, so the worker can correct it.
def _clip(text, key: str) -> str:
    try:
        from widgets import presentation
        return presentation.clip(text, presentation.contract(WIDGET_ID)[key])[0]
    except Exception:
        return "" if text is None else str(text)[:220]


# STORAGE caps for the card's slots (V2-797). They used to be LAYOUT budgets (title 34, subtitle 70): what the card
# was assumed to fit, so every real listing name was cut on the server and reported as breaking the card. The card
# now clamps to the space it really has and shows the whole text on expand; what is bounded here is only how much
# one field may hold (`presentation.DEFAULTS`), on a word boundary and marked with "…".
_SLOT_CLIP_KEYS = {"title": "title", "subtitle": "subtitle", "price": "price", "badge": "badge"}


def _clip_slot(text, key: str) -> str:
    clipped = _clip(text, key)
    if clipped:
        return clipped
    return "" if text is None else str(text)[:300]


def _clean_part(raw: dict) -> dict | None:
    if not isinstance(raw, dict):
        return None
    p: dict = {}
    for k in _PART_FIELDS:
        v = raw.get(k)
        if v is None or v == "":
            continue
        if k == "lines":
            p[k] = _clean_lines(v, _MAX_PART_LINES)
        elif k == "facts":
            f = _clean_facts(v)
            if f:
                p[k] = f
        elif k == "title":
            p[k] = _clip_slot(v, "part_title")
        else:
            p[k] = str(v)[:300]
    return p if p.get("title") else None      # a piece with no name can't be shown or talked about


def _clean_parts(raw) -> list[dict]:
    if not isinstance(raw, (list, tuple)):
        return []
    out = []
    for r in raw:
        p = _clean_part(r)
        if p:
            out.append(p)
    return out[:_MAX_PARTS]


def _clean_item(raw: dict) -> dict | None:
    if not isinstance(raw, dict):
        return None
    it: dict = {}
    for k in _ITEM_FIELDS:
        v = raw.get(k)
        if v is None or v == "":
            continue
        if k == "primary":
            it[k] = bool(v)
        elif k == "lines":
            it[k] = _clean_lines(v, _MAX_LINES)
        elif k == "parts":
            p = _clean_parts(v)
            if p:
                it[k] = p
        elif k == "images":
            img = _clean_images(v)
            if img:
                it[k] = img
        elif k == "facts":
            f = _clean_facts(v)
            if f:
                it[k] = f
        elif k == "meta":
            m = _clean_meta(v)
            if m:
                it[k] = m
        elif k == "blocks":
            b = _clean_blocks(v)
            if b:
                it[k] = b
        elif k == "score":
            s = _clean_score(v)
            if s:
                it[k] = s
        elif k == "full_title":
            it[k] = str(v).strip()[:1000]          # the listing's own words: its own, larger cap (V2-797)
        elif k in _SLOT_CLIP_KEYS:
            it[k] = _clip_slot(v, _SLOT_CLIP_KEYS[k])
            if k == "title" and it[k] != str(v).strip():
                it.setdefault("full_title", str(v).strip()[:1000])
        else:
            it[k] = str(v)[:300]
    return it if it.get("title") else None       # a card with no title is not a result, it is noise


def _clean_items(raw) -> list[dict]:
    if not isinstance(raw, (list, tuple)):
        return []
    out = []
    for r in raw:
        it = _clean_item(r)
        if it:
            out.append(it)
    return out[:_MAX_ITEMS]


def _clean_source(raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    s: dict = {}
    for k in _SOURCE_FIELDS:
        v = raw.get(k)
        if v is None or v == "":
            continue
        if k == "found":
            n = _num(v)
            if n is not None:
                s[k] = int(n)
        elif k == "status":
            st = str(v).strip().lower()
            s[k] = st if st in _SOURCE_STATUS else "ok"
        elif k == "detail":
            s[k] = _clip(v, "source_detail") or str(v)[:_MAX_DETAIL_CHARS]
        else:
            s[k] = str(v)[:300]
    if not s.get("name") and s.get("url"):
        s["name"] = s["url"].split("//")[-1].split("/")[0]      # without a name, the domain identifies the source
    if not s.get("name"):
        return None                              # a source that cannot be named cannot be read or audited
    s.setdefault("status", "ok")
    return s


def _clean_sources(raw) -> list[dict]:
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return []
    out = []
    for r in raw:
        s = _clean_source(r)
        if s:
            out.append(s)
    return out[:_MAX_SOURCES]


def _clean_rejected(raw) -> list[dict]:
    """Candidates that were LOOKED AT and left out, each with its reason. Same posture as `_clean_source`:
    a row that cannot be named, or that does not say why it lost, is dropped rather than half-stored."""
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return []
    out = []
    for r in raw:
        if not isinstance(r, dict):
            continue
        row: dict = {}
        for k in _REJECTED_FIELDS:
            v = r.get(k)
            if v is None or v == "":
                continue
            row[k] = str(v)[:_MAX_WHY_CHARS if k == "why" else 300]
        if row.get("title") and row.get("why"):
            out.append(row)
    return out[:_MAX_REJECTED]


def _clean_summary(raw) -> dict:
    if not isinstance(raw, dict):
        return {}
    out: dict = {}
    for k in _SUMMARY_NUMS:
        n = _num(raw.get(k))
        if n is not None and n >= 0:
            out[k] = int(n)
    for k in _SUMMARY_TEXT:
        if raw.get(k):
            out[k] = _clip(raw[k], "sheet_subtitle") or str(raw[k])[:220]
    steps = raw.get("steps")
    if isinstance(steps, str):
        steps = [steps]
    if isinstance(steps, (list, tuple)):
        clean = [str(x)[:_MAX_STEP_CHARS] for x in steps if x not in (None, "")][:_MAX_STEPS]
        if clean:
            out["steps"] = clean
    return out


def _clean_criteria(raw) -> dict:
    if not isinstance(raw, dict):
        return {}
    out: dict = {}
    for k in ("goal", "domain"):
        if raw.get(k):
            out[k] = str(raw[k])[:400]
    for k in _CRIT_LISTS:
        v = raw.get(k)
        if isinstance(v, str):
            v = [v]
        if isinstance(v, (list, tuple)):
            clean = [str(x)[:_MAX_CRIT_CHARS] for x in v if x not in (None, "")][:_MAX_CRIT]
            if clean:
                out[k] = clean
    if isinstance(raw.get("subjects"), (list, tuple)):       # declared by the brief; empty = it named none
        out["subjects"] = [str(x)[:60] for x in raw["subjects"] if str(x or "").strip()][:6]
    n = _num(raw.get("min_candidates"))
    if n is not None and n > 0:
        out["min_candidates"] = int(n)
    n = _num(raw.get("n_final"))
    if n is not None and n > 0:
        out["n_final"] = int(n)
    return out
