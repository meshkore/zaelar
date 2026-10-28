"""widgets/results/clean.py — how a pushed payload becomes the sheet's closed schema: the fields an item,
a part, a source, a rejected row, the summary and the criteria may carry, their caps, and the word-boundary clip.
`data` re-exports every name (`data._clean_item`, `data._MAX_ITEMS`).
"""
import unicodedata as _ud
from html.parser import HTMLParser

from .record import (  # noqa: F401
    _MAX_FACTS, _MAX_LINES, _clean_blocks, _clean_facts, _clean_images, _clean_lines, _clean_meta, _clean_score, _num)
from .sheet_names import WIDGET_ID


# Fields an item may carry; anything else is dropped. The payload comes from a worker that read the open web,
# so the schema stays closed even though widget.js paints with textContent only.
_ITEM_FIELDS = ("title", "subtitle", "price", "badge", "url", "image", "primary", "lines",
                "parts", "images", "facts", "score", "blocks", "full_title", "meta", "kind")

#: WHAT KIND OF THING a result is — content, not layout. On the payload's root it names the list; on an item (V2-831)
#: it picks that card's template (`offer` · `video` · `link`, `js/parts.js::itemKind`). Absent, the shape decides.
_KINDS = ("product", "place", "media", "photo", "document", "link", "plan", "offer", "video")
#: `full_title` — the title as the listing wrote it, kept when the slot clips it: the card paints `title`,
#: a reader of the row reads both, so what the clip cut is not lost to later turns.
# A PART is one piece of a composite item (the hotel inside a holiday plan, the ferry, the restaurant). Same
# closed-schema discipline; `kind` is the piece's role ("Hotel", "Ferry", "Restaurante") so the card can label it.
_PART_FIELDS = ("kind", "title", "subtitle", "price", "url", "image", "lines", "facts")

_MAX_ITEMS = 60          # a report the operator can actually read; widget.js renders the first 24 and says how many more
# `_MAX_LINES` fits a whole block of text (a song's lyrics) in one item, still bounded so a worker can't paste
# an entire scraped page into a card.
_MAX_PARTS = 6           # a plan is a handful of pieces (hotel+ferry+restaurant), never a list in disguise
_MAX_PART_LINES = 20
# A SOURCE is an origin that was attempted, with what HAPPENED there. Status is a closed vocabulary because colour
# and reading depend on it: "could not enter" and "entered but capped at 50" are different outcomes.
_SOURCE_FIELDS = ("name", "url", "status", "detail", "found")
_SOURCE_STATUS = ("ok", "partial", "auth", "blocked", "error", "pending")
_MAX_SOURCES = 40
_MAX_DETAIL_CHARS = 200

# SUMMARY: state + counts + what was done. `explored`/`selected`/`discarded` are REPORTED by the worker (only it
# knows what it looked at); what can be derived is derived and labelled as such (see `_counts`).
_SUMMARY_NUMS = ("explored", "selected", "discarded", "round")

# REJECTED candidates, by name: (what, where, why it lost). A row with no `why` is not stored — names without
# reasons are not an audit. Capped well above the kept list: the cap bounds the sheet on disk, not how much
# looking is enough (V2-728).
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


# ── PRESENTATION QUALITY CONTROL ── budgets live in `widgets/presentation.py` (shared by every blank surface).
# Clipping is on WORD boundaries and marked (an amputated caveat misleads more than its absence); a payload that
# breaks the card is logged and returned in the action response so the worker can correct it.
def _clip(text, key: str) -> str:
    try:
        from widgets import presentation
        return presentation.clip(text, presentation.contract(WIDGET_ID)[key])[0]
    except Exception:
        return "" if text is None else str(text)[:220]


# STORAGE caps for the card's slots, not layout budgets: the card clamps to its real space and shows the whole
# text on expand; here only how much one field may hold is bounded (`presentation.DEFAULTS`) (V2-797).
_SLOT_CLIP_KEYS = {"title": "title", "subtitle": "subtitle", "price": "price", "badge": "badge"}


class _TextOnly(HTMLParser):
    """The text of a fragment of markup, tags parsed away (any tag, no pattern)."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []

    def handle_data(self, data):
        self.out.append(data)

    def handle_starttag(self, tag, attrs=None):
        self.out.append(" ")
    handle_endtag = handle_starttag


def _plain(text) -> str:
    """A text slot holds TEXT (V2-831): scraped markup (`6,69 € /mes<br>`) and entities go, whitespace collapses."""
    s = "" if text is None else str(text)
    if "<" in s or "&" in s:
        p = _TextOnly()
        try:
            p.feed(s), p.close()
            s = "".join(p.out)
        except Exception:  # noqa: BLE001 — unparseable markup keeps its raw text rather than losing the row
            pass
    return " ".join(s.split())


def _split(it: dict) -> tuple[str, str, bool]:
    """(its amount, the rest of the title, is it a NAME?) — V2-831, structural, no vocabulary: a name comes BEFORE
    its amount. A title starting with its own price, leading with a number next to a currency sign, or that is only
    an amount is the price line of something else. Bare digits with no currency («1984») are still a name."""
    t, price = str(it.get("title") or ""), _plain(it.get("price"))
    if price and t.startswith(price):
        return price, t[len(price):], False
    i = next((i for i, ch in enumerate(t) if _ud.category(ch).startswith("L")), len(t))
    money = any(_ud.category(c) == "Sc" for c in t[:i])
    named = (not money) if i == len(t) else not (money and any(c.isdigit() for c in t[:i]))
    return price or t[:i].strip(" ·-–—"), t[i:], named


def _fold(into: dict, label: str, rest: str) -> None:
    """A nameless row is a price OPTION of the named row before it: one fact {its amount: the rest of its line}."""
    value, facts = rest.strip(" -–—·") or label, list(into.get("facts") or [])
    if label and len(facts) < _MAX_FACTS and {"label": label[:80], "value": value} not in facts:
        into["facts"] = facts + [{"label": label[:80], "value": value}]


def _clip_slot(text, key: str) -> str:
    text = _plain(text)
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
        elif k in ("subtitle", "price"):
            p[k] = _plain(v)[:300]
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
            it[k] = [x for x in map(_plain, _clean_lines(v, _MAX_LINES)) if x]
        elif k == "kind":
            if str(v).strip().lower() in _KINDS:
                it[k] = str(v).strip().lower()
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
            it[k] = _plain(v)[:1000]               # the listing's own words: its own, larger cap (V2-797)
        elif k in _SLOT_CLIP_KEYS:
            it[k] = _clip_slot(v, _SLOT_CLIP_KEYS[k])
            if k == "title" and it[k] != _plain(v):
                it.setdefault("full_title", _plain(v)[:1000])
        else:
            it[k] = str(v)[:300]
    return it if it.get("title") else None       # a card with no title is not a result, it is noise


def _clean_items(raw) -> list[dict]:
    """THE DOOR every item crosses (present, append, every read). V2-831: a row with no name is not a result — the
    price lines a scraper lifted under one offer (`6,69 € /mes - Ahorra un 25%`) fold into the named row before
    them as facts, and with no named row before them they are dropped. An empty item never gets this far."""
    if not isinstance(raw, (list, tuple)):
        return []
    out: list[dict] = []
    for it in filter(None, map(_clean_item, raw)):
        label, rest, named = _split(it)
        if named:
            out.append(it)
        elif out:
            _fold(out[-1], label, rest)
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
