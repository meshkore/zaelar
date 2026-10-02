#
# results widget — backend. INTENTIONALLY does no searching of its own: it is the GENERIC PRESENTATION SURFACE of
# zaelar. Whoever DID the work (a Brain Worker that searched the web, the browser, the FlashBrain) hands it a
# finished result set and this widget just PERSISTS and RENDERS it. Works the same for pools, cars, holidays,
# open-source projects, emails, files — it never knows nor cares what the items are about.
#
# HOW IT GETS FILLED (the only way; there is no other channel):
#   a Brain Worker →  python -m nucleo.widget_cli data results present '{"title": "...", "items": [...]}'
#   the FlashBrain →  tool widget_data(widget_id="results", action="present", payload={...})
# Both land on apply_action() below → store.save() → the single SSE "this widget changed" event → the open card
# re-fetches view_data() and re-renders. Because the payload is PERSISTED (not ephemeral), it survives the
# re-render, a reconnect and a server restart — the operator does not lose a report he already paid for.
#
# HISTORY (2026-08-02): view_data() used to return a hardcoded demo list of the operator's projects
# (Pricewaterhouse / Mage Core / MeshKore…). Showing the widget for a pool search therefore painted "Proyectos" —
# which is exactly what the operator saw and reported ("I only see the projects widget open; it has nothing to do
# with this"). A generic presentation surface has NO content of its own: with nothing pushed it is an EMPTY
# SHEET, never someone else's data.
#
# HISTORY (2026-08-09): a result was strictly FLAT — one card = one thing. That cannot express what a real
# research answer looks like: the operator asked for holiday PROPOSALS, and a proposal is a BUNDLE (this hotel +
# that ferry crossing + maybe a restaurant), each piece with its own price, photo, link and times. Flattening a
# bundle into free text loses the structure the operator wants to compare on. So an item may now carry `parts`
# (the pieces it is made of) plus, for the DRILL-DOWN, `images`/`facts` (a photo gallery and the label→value
# sheet: check-in, port, cancellation policy...). And `view`/`focus` give the sheet a SECOND PAGE: "show me proposal
# 1 in detail" switches this same widget to the full dossier of one item instead of the compact grid.
#
# HISTORY (2026-08-12) — THE SHEET HAS FOUR TABS, not only the list. Operator rule: this surface will be used
# generically for MANY complex searches, and a complex search is not just its result. It is also HOW it is going, WITH
# WHICH criteria, and WHERE the data comes from. Until today the last three only existed verbally —you had to ask the
# agent— and therefore could not be checked:
#
#   · RESULTS (the important one) — cards, and a card's full record when opened.
#   · SUMMARY — work status + how many candidates were explored, how many remain on screen, what was done.
#   · SOURCES — which websites it entered and WHAT HAPPENED on each one: entered, could not due to auth, limited to
#               50 results, errored. This turns "I found nothing" into auditable data.
#   · CRITERIA — the task as currently executed (hard/soft/assumed/rubric) PLUS corrections the operator gives by
#                voice ("they should be 42 to 49 feet"). Seeded automatically from the BRIEF (`nucleo/research.py`),
#                so they do not depend on the worker remembering to write them.
#
# All four live in the SAME persisted payload as the list, and so does the active tab (`tab`) — just like
# `view`/`focus`: this way "show me where you got this from" is a voice command that moves the screen, and state
# survives re-render, reconnect, and restart. Zero new protocol: everything enters through DECLARED actions.
#
# And the RECORD is DYNAMIC (`blocks`): each result type needs to be shown differently — a boat does not read like a
# paper or an email. Instead of a fixed schema (which forces anything that does not fit into prose) or raw worker HTML
# (an injection waiting to happen: this payload comes from the open web), an item may bring a LIST OF BLOCKS from a
# closed vocabulary —text, facts, tags, gallery, meter, table, link, section— that the surface paints with
# `textContent`. Same composition freedom without handing the surface to a third party.
#
import re as _re
import time as _tm
import unicodedata as _ud

from .. import store
from widgets import hint_lang as _hl   # V2-778 F3-30: hints are read back aloud, in the agent's language
from .sheet_names import (  # noqa: F401 — re-export: this module IS the sheet contract
    WIDGET_ID, _INSTANCE_SEP, _MAX_SHEETS, _safe_sheet, card_face, instance_id, prune_sheets, recent_faces,  # noqa: F401
    sheet_key, sheets)

# How one VALUE from a payload becomes something paintable — the rating, the photos, the lines and the closed
# block vocabulary of a dynamic record (`widgets/results/record.py`, V2-702; moved byte for byte to pay the
# ratchet). Re-exported because this module is the sheet's contract: callers and tests keep saying `data._MAX_LINES`.
from .record import (  # noqa: F401,E402 — re-export
    _BLOCK_KINDS, _MAX_BLOCKS, _MAX_CELL_CHARS, _MAX_CHIPS, _MAX_FACT_CHARS, _MAX_FACTS, _MAX_IMAGES,
    _MAX_LINE_CHARS, _MAX_LINES, _MAX_TABLE_COLS, _MAX_TABLE_ROWS,
    _clean_block, _clean_blocks, _clean_facts, _clean_images, _clean_lines, _clean_score, _num)


# Fields an item may carry. Anything else pushed is dropped — the payload comes from a worker that read the open
# web, so we never let arbitrary keys through to the renderer (widget.js paints with textContent only, but the
# schema is the contract and it stays closed).
_ITEM_FIELDS = ("title", "subtitle", "price", "badge", "url", "image", "primary", "lines",
                "parts", "images", "facts", "score", "blocks")
# A PART is one piece of a composite item (the hotel inside a holiday plan, the ferry, the restaurant). Same
# closed-schema discipline; `kind` is the piece's role ("Hotel", "Ferry", "Restaurante") so the card can label it.
_PART_FIELDS = ("kind", "title", "subtitle", "price", "url", "image", "lines", "facts")

_MAX_ITEMS = 60          # a report the operator can actually read; widget.js renders the first 24 and says how many more
# `lines` used to cap at 4 — fine for a spec-sheet bullet list, but a real request ("show me the lyrics to X") needs
# a whole song's worth of text in ONE item's body (2026-08-03). Raised so a full block of text fits; still bounded
# so a worker can't paste an entire scraped page into a card.
_MAX_PARTS = 6           # a plan is a handful of pieces (hotel+ferry+restaurant), never a list in disguise
_MAX_PART_LINES = 20

# ── THE TABS THAT ARE NOT THE LIST ───────────────────────────────────────────────────────────────────────────
# «process» IS a tab like the others: if the operator selects it, the choice PERSISTS just like the others. It was
# missing from this tuple and the click returned `{"ok": false, "error": "pestaña «process» desconocida"}` —the tab
# was rendered (the widget switches it immediately), and on the next data refresh, which arrives with each phase
# during a live task, the derived state carried it back to Results. An unsaved click does not fail noisily: it fails
# by pulling the operator away from where they chose to look (V2-227 C).
_TABS = ("process", "results", "summary", "sources", "criteria")

#: WHAT KIND OF THING the sheet found. This is CONTENT, not layout — which is the whole reason it is allowed to
#: come from outside. `widgets/presentation.py` rule 1 says the surface owns the layout and whoever fills it must
#: not send `columns`; saying «these are products» breaks none of that: it is a fact about the results, and
#: `widget.js::layoutFor` is still the one that turns it into a shape (photo left / gallery / plain rows). Absent
#: or unknown, the shape of the items decides on its own, exactly as before.
_KINDS = ("product", "place", "media", "photo", "document", "link", "plan")

#: WHICH TEMPLATE the list is drawn with. V2-703, and a deliberate reversal of `presentation.py` rule 1 («the
#: surface owns the layout»), by the operator's explicit decision: «tenemos varias [plantillas] que le ofrecemos
#: al Brainworker para que elija la más adecuada para cada lista de resultados […] sí debe elegir ese formato y
#: colocar dentro los datos que sean relevantes».
#:
#: The reason rule 1 existed has NOT gone away, so it survives as a guard instead of a veto. What the worker may
#: send is a NAME out of this closed set — never a width, a column count or a pixel — and `widget.js` refuses one
#: it cannot honour (a photo template over results with no photos) instead of drawing it badly. That is the line:
#: the worker chooses the SHAPE and fills the slots; the surface still owns the geometry of each slot.
_LAYOUTS = ("card", "tile", "row", "list", "compare", "split", "gallery", "rows")

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


# Card slots the audit measures (presentation.audit): what is stored must fit them, or the card wraps and
# breaks no matter what the worker was told (session 6d19df41: 5 «el payload rompe la tarjeta» warnings while
# the overlong titles were persisted verbatim). The audit still runs on the RAW payload and reports the issue
# back to the worker — this only bounds what reaches the card, on a word boundary and marked with "…".
_SLOT_CLIP_KEYS = {"title": "title", "subtitle": "subtitle", "price": "price", "badge": "badge"}


def _clip_slot(text, key: str) -> str:
    clipped = _clip(text, key)
    if clipped:
        return clipped
    return "" if text is None else str(text)[:300]


def _audit(payload: dict) -> list[str]:
    try:
        from widgets import presentation
        issues = presentation.audit(WIDGET_ID, payload)
    except Exception:
        return []
    if issues:
        try:
            from voice.observer import emit
            emit("widget", "🎨 presentación: el payload rompe la tarjeta", text=" · ".join(issues)[:400],
                 role="system", extra={"id": WIDGET_ID, "n": len(issues), "issues": issues[:12]})
        except Exception:
            pass
    return issues


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
        elif k == "blocks":
            b = _clean_blocks(v)
            if b:
                it[k] = b
        elif k == "score":
            s = _clean_score(v)
            if s:
                it[k] = s
        elif k in _SLOT_CLIP_KEYS:
            it[k] = _clip_slot(v, _SLOT_CLIP_KEYS[k])
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
    n = _num(raw.get("min_candidates"))
    if n is not None and n > 0:
        out["min_candidates"] = int(n)
    n = _num(raw.get("n_final"))
    if n is not None and n > 0:
        out["n_final"] = int(n)
    return out


def _empty() -> dict:
    return {"title": "Resultados", "subtitle": "", "items": []}


# The live PROCESS lives in `widgets/results/live.py` (V2-296): everything there is derived from the dispatcher's
# record, while this module contains the sheet's content. It is re-exported because this is a move, not an interface
# change —the tests and `view_data` continue calling these names as before.
from widgets.results.live import (  # noqa: E402,F401 — re-export
    _MAX_PHASES, _MAX_PHASE_CHARS, _browser, _clean_phases, _harvest, _progress)


def _counts(data: dict) -> dict:
    """DERIVED counts, intentionally separate from reported ones. "How many were explored" is only known by the
    worker (reported in summary); "how many are on screen" and "how many sources" are known by the sheet. Mixing them
    into one number would invent half of it: if nobody reported breadth, the summary SAYS so instead of showing the
    number of cards as if it were the explored count."""
    items = data.get("items") or []
    sources = data.get("sources") or []
    summary = data.get("summary") or {}
    ok = [s for s in sources if s.get("status") in ("ok", "partial")]
    got = sum(int(s.get("found") or 0) for s in sources)
    return {
        "shown": len(items),
        "sources": len(sources),
        "sources_ok": len(ok),
        "sources_failed": len([s for s in sources if s.get("status") in ("auth", "blocked", "error")]),
        "from_sources": got,                     # candidates seen ACCORDING TO reported sources
        "explored": summary.get("explored"),     # what the worker declares to have truly evaluated
        "selected": summary.get("selected", len(items) or None),
    }


def view_data(q: str = "") -> dict:
    """The LAST result set pushed here, verbatim. Nothing pushed yet → an empty sheet (never invented content).

    `q` is the INSTANCE (V2-259): the canvas already splits `results::<corr>` and hands the suffix over as `q`
    (`desktop.js::show`), so this signature did not have to change — it just stopped ignoring the argument.
    """
    db = store.load(sheet_key(q), _empty())
    if not isinstance(db, dict):
        db = _empty()
    data = dict(db)
    data.setdefault("title", "Resultados")
    data["items"] = _clean_items(data.get("items"))
    data["sources"] = _clean_sources(data.get("sources"))
    data["summary"] = _clean_summary(data.get("summary"))
    data["criteria"] = _clean_criteria(data.get("criteria"))
    if data.get("tab") not in _TABS:
        data.pop("tab", None)                    # without a valid tab, results wins (the widget decides)
    # V2-591: a scroll request EXPIRES — re-applying a stale one on a reload would move what the operator is
    # reading with no order behind it. 120 s covers the voice round-trip with margin.
    _sc = data.get("scroll") or None
    if _sc:
        if not (float(_sc.get("at") or 0) and (_tm.time() - float(_sc.get("at") or 0)) <= 120):
            data.pop("scroll", None)
    data["empty"] = not data["items"]                # V2-776 L2 — the harness reads emptiness, never guesses it
    if not data["items"]:
        data.setdefault("note", "Sin resultados todavía.")
        data.pop("view", None)                   # no items ⇒ there is nothing to be showing the detail OF
        data.pop("focus", None)
    stored = _clean_phases(data.get("process"))
    if stored:
        data["process"] = stored
    else:
        data.pop("process", None)            # without history, the blank sheet remains blank
    data["counts"] = _counts(data)
    data["progress"] = _progress(data, _safe_sheet(q))
    data["harvest"] = _harvest(data, _safe_sheet(q))
    data["browser"] = _browser(data, _safe_sheet(q))     # V2-571: the process tab embeds the errand's browser
    data["identity"] = _identity()                       # V2-601 T-10: rides the payload; widget.js may not fetch
    return data


def _identity() -> dict:
    """Install + session ids for the SUMMARY tab's audit strip (V2-538). Served IN the payload because the
    widget contract bans network in widget.js — the strip's own fetch was the violation that kept
    `make test-widgets` permanently red (V2-601 T-10). Fail-open to {}: no identity, no strip, as before.
    (The engine import below is why `results` sits in the validator's curated `_STDLIB_EXEMPT`, with the
    observer emit of `_audit` — this widget IS an engine surface, the errand sheet.)"""
    try:
        from observability import identity as _ident
        info = _ident.session_info() or {}
        return {"user_id": str(_ident.user_id() or ""), "session_id": str(info.get("id") or "")}
    except Exception:  # noqa: BLE001
        return {}


def _save(data: dict, sheet: str = "") -> None:
    """Persist WITHOUT derived fields: `counts` is recalculated on read, and storing it would make it stale as soon as
    anything else changes (an old number on screen is worse than no number)."""
    d = dict(data)
    d.pop("counts", None)
    d.pop("progress", None)                  # derived from the live record: storing it would freeze a «Trabajando…»
    d.pop("browser", None)                   # derived too (V2-571): a stored capture would outlive its browser
    d.pop("identity", None)                  # derived every read (T-10): ids belong to the PROCESS, not the sheet
    for k in ("sources", "summary", "criteria"):
        if not d.get(k):
            d.pop(k, None)                       # remove empty sections: the blank sheet remains blank
    store.save(sheet_key(sheet), d)


def _named(payload: dict) -> str:
    """The item a payload names, under whichever key the caller used. Demo pass 2026-09-28 (S3): «open the one
    that's the best deal» arrived as `detail {"item": "Dell S2725QS"}` — the name of the first row, under the
    key other cards (map, youtube) use for a row — and was answered «I can't find that result on the sheet»."""
    for k in ("title", "item", "name"):
        v = payload.get(k)
        if isinstance(v, str) and v.strip():
            return v
    return ""


def _find(items: list[dict], title: str = "", index=None) -> dict | None:
    """Resolve WHICH item the operator means. By exact title, else by a forgiving contains-match, else by ordinal.
    The ordinal matters because this arrives from VOICE: "show me proposal number one" is far more likely to
    survive STT intact than a hotel's full commercial name, so the caller may pass index=1 instead of a title."""
    if isinstance(index, (int, float)) and not isinstance(index, bool):
        i = int(index)
        if 1 <= i <= len(items):                 # 1-based: the operator counts from one, not from zero
            return items[i - 1]
    t = (title or "").strip().lower()
    if not t and isinstance(index, str) and not index.strip().isdigit():
        t = index.strip().lower()           # a reference in words arrived in the index slot (the resolver's habit)
    elif not t and isinstance(index, str) and index.strip().isdigit():
        i = int(index.strip())
        if 1 <= i <= len(items):
            return items[i - 1]
    if not t:
        return None
    for it in items:
        if (it.get("title") or "").strip().lower() == t:
            return it
    for it in items:
        if t in (it.get("title") or "").strip().lower():
            return it
    # Demo pass 63, S3: «open the one that's the best deal» arrived as title «KTC H27P22S — $254.98» — the compare
    # view's own line, title AND price — and neither match above holds. The head before the decoration is the title;
    # and a row whose whole title sits inside the reference is named by it (one such row, never a guess).
    head = _re.split(r"\s+[—–|·]\s+|\s+-\s+", t, maxsplit=1)[0].strip()
    if head and head != t:
        for it in items:
            if (it.get("title") or "").strip().lower() == head:
                return it
        for it in items:
            if head in (it.get("title") or "").strip().lower():
                return it
    inside = [it for it in items if (tt := (it.get("title") or "").strip().lower()) and len(tt) >= 6 and tt in t]
    if len(inside) == 1:
        return inside[0]
    # …and by the BADGE the sheet shows him (V2-776, verification 2026-09-27): «Open the best value option» over a
    # sheet whose cards say BEST VALUE / BEST REVIEWED / CHEAPEST found nothing — only titles and ordinals were
    # read, and the words he used are printed on the card itself. One badge named = that item; two = no guess.
    named = [it for it in items if (b := str(it.get("badge") or "").strip().lower()) and b in t]
    return named[0] if len(named) == 1 else None


# ── THE TASK OPENS AND CLOSES THE SHEET (V2-227 scope C · extracted to `widgets/results/lifecycle.py`, V2-530) ─
# The three gateways the dispatcher uses so the operator can SEE the work as it proceeds. They are not actions in
# `apply_action`'s vocabulary: no prompt requests them; the task lifecycle triggers them —putting them there would
# expose them to a worker, which is precisely who must not decide when the sheet is opened.
# They are re-exported here —the same move and gesture as `live.py` (V2-296)— because this module IS the sheet's
# contract for everyone using it: callers continue saying `data.begin_task`.
from widgets.results.lifecycle import (  # noqa: E402,F401 — re-export
    begin_task, end_task, rename_task)


def _sheets_for_brain(sheet) -> list[str]:
    """WHICH sheets the brain sees. With `sheet` given, that one; without it, ALL that exist.

    Making the default «all» is deliberate, and the opposite fails silently: with two live tasks, reading only one
    would leave the turn answering confidently about the wrong sheet —«¿el hotel de la propuesta 2 tiene wifi?»
    resolved against the plumber's search— with nothing indicating another existed. It is the same kind of lie that
    V2-257 removed from the card: not a smaller truth, but a different and false one.
    """
    if sheet is not None and _safe_sheet(sheet):
        return [_safe_sheet(sheet)]
    if sheet == "":
        return [""]
    found = sheets()
    return found or [""]


def ref_index(sheet=None) -> list[dict]:
    """The items currently ON SCREEN, so the brain can (a) let the operator pick one by talking about it ("keep
    the beach club one") and (b) — just as important — SEE that the sheet is empty. Before this, an open but
    blank results card was indistinguishable from a card that simply doesn't publish its items, and the brain
    answered "here it is" over an empty screen (real session, 12:57:57).

    The hint leads with the ORDINAL because that is how the operator refers to a proposal out loud ("number two");
    without it the brain had to guess which card "the second one" was.

    V2-259 — with several sheets open, each reference says WHICH ONE it belongs to. The ordinal only disambiguates
    within a sheet: «number two» with two searches on screen refers to two different things, and without the task
    in front of it the turn would silently choose one.
    """
    out = []
    todas = _sheets_for_brain(sheet)
    varias = len(todas) > 1
    for sid in todas:
        data = view_data(sid)
        titulo = str(data.get("title") or "").strip()
        for n, it in enumerate(data.get("items", []), 1):
            bits = [f"#{n}"]
            if varias and titulo:
                bits.append(_hl.pick(f"de «{titulo}»", f"from «{titulo}»"))
            if it.get("price"):
                bits.append(it["price"])
            if it.get("parts"):
                bits.append(" + ".join(p.get("kind") or p.get("title") or "" for p in it["parts"]))
            elif it.get("subtitle"):
                bits.append(it["subtitle"])
            out.append({"id": it["title"], "label": it["title"], "field": "title",
                        "sheet": sid, "hint": " · ".join(b for b in bits if b)})
    return out


# V2-287 — the prompt digest lives in its own module (`digest.py`): pure functions over a sheet dict, with no store
# and no writes. The two names that DO need storage remain here —which sheets exist and what is inside them—, and
# `_digest_head`/`_digest_one` remain re-exported because they are the contract already used by the surface tests.
from . import digest as _digest                                                              # noqa: E402
from .digest import head as _digest_head, one as _digest_one, _MAX_HEAD_CHARS, _MAX_HEAD_ITEM  # noqa: E402,F401


def prompt_digest(sheet=None) -> str:
    """What is ACTUALLY on screen, compact enough to ride in every prompt while this widget is open.

    Why this exists: `ref_index()` only publishes title+hint, so the brain could name the items but knew nothing
    about them. Asked "does the hotel in proposal 2 have wifi?" — about a result already on screen, whose own
    card says so — it had to either guess or escalate a whole new search for a fact it was already holding. That
    is the difference between a screen the agent can SEE and one it merely painted. Bounded on purpose: this is
    a digest for reasoning over, not the full dossier (that lives in the detail view).

    V2-259 — with several sheets, ALL are traversed and each block opens with the task it belongs to. The alternative
    (keeping one) gives no warning: the turn would confidently answer about the wrong search, the same kind of lie
    that V2-257 removed from the card. The item limit is PER SHEET.
    """
    todas = _sheets_for_brain(sheet)
    if len(todas) > 1:
        bloques = []
        for sid in todas:
            d = view_data(sid)
            t = str(d.get("title") or "").strip() or "(sin título)"
            bloques.append(f"── HOJA «{t}» ──\n" + _digest.one(d))
        return "\n".join(bloques)
    return _digest.one(view_data(todas[0]))


# The tab arrives by VOICE ("show me the sources", "how is it going?"), so the name comes in the operator's language
# and through STT. This is not an intent table —the model decides that— but normalization of the argument it already
# chose: the same role the ordinal plays in `detail`.
_TAB_ALIASES = {
    "resultados": "results", "resultado": "results", "lista": "results", "fichas": "results",
    "sumario": "summary", "resumen": "summary", "estado": "summary", "progreso": "summary",
    "fuentes": "sources", "fuente": "sources", "webs": "sources", "paginas": "sources", "páginas": "sources",
    "criterios": "criteria", "criterio": "criteria", "brief": "criteria", "encargo": "criteria",
    "proceso": "process", "process": "process", "curso": "process", "avance": "process",
}


def _merge_sections(data: dict, payload: dict) -> None:
    """`sources`/`summary`/`criteria` delivered ALONGSIDE present/append. They are merged over what already existed:
    whoever delivers results does not always have in front of them what they reported five minutes ago."""
    src = _clean_sources(payload.get("sources"))
    if src:
        cur = list(data.get("sources") or [])
        for s in src:
            key = (s.get("url") or "").strip().lower() or (s.get("name") or "").strip().lower()
            hit = next((c for c in cur
                        if ((c.get("url") or "").strip().lower() or (c.get("name") or "").strip().lower()) == key),
                       None)
            if hit:
                hit.update(s)
            else:
                cur.append(s)
        data["sources"] = cur[:_MAX_SOURCES]
    summ = _clean_summary(payload.get("summary"))
    if summ:
        cur = dict(data.get("summary") or {})
        steps = list(cur.get("steps") or []) + [s for s in summ.pop("steps", []) if s not in (cur.get("steps") or [])]
        cur.update(summ)
        if steps:
            cur["steps"] = steps[-_MAX_STEPS:]
        data["summary"] = cur
    crit = _clean_criteria(payload.get("criteria"))
    if crit:
        cur = dict(data.get("criteria") or {})
        cur.update(crit)
        data["criteria"] = cur
    # The rejected pile GROWS across rounds (a worker reports as it goes) and dedupes on url-or-title, by
    # the same rule `append` uses for the kept list: the same finding reported twice is one finding.
    rej = _clean_rejected(payload.get("rejected"))
    if rej:
        cur = list(data.get("rejected") or [])
        seen = {(x.get("url") or x.get("title") or "").strip().lower() for x in cur}
        for r in rej:
            key = (r.get("url") or r.get("title") or "").strip().lower()
            if key and key not in seen:
                seen.add(key)
                cur.append(r)
        data["rejected"] = cur[:_MAX_REJECTED]


# V2-778 F1-12 — the action handlers live in `actions.py`, imported back under their names (that module
# reads this one).
from .actions import (  # noqa: E402,F401
    _a_present, _a_append, _a_clear, _a_choose, _a_detail, _a_list, _a_scroll, _a_layout, _a_tab, _a_sources,
    _a_rejected, _a_progress, _a_criteria, _a_auth_done)


# V2-778 F1-12 — one function per action (in `actions.py`), and `apply_action` is the table lookup. Each body
# is the branch it was, moved verbatim; the contract gate reads the table's keys
# (`widgets/validator._table_actions`).


ACTIONS = {
    "present": _a_present,
    "append": _a_append,
    "clear": _a_clear,
    "choose": _a_choose,
    "detail": _a_detail,
    "list": _a_list,
    "scroll": _a_scroll,
    "layout": _a_layout,
    "tab": _a_tab,
    "sources": _a_sources,
    "rejected": _a_rejected,
    "progress": _a_progress,
    "criteria": _a_criteria,
    "auth_done": _a_auth_done,
}


# present/append/clear = how the result set is delivered. `choose` lets the operator PICK one of the shown items
# (e.g. "quiero esa"); unlike before it now PERSISTS the pick, because the list itself is persisted — the old
# comment about avoiding store.save() described the ephemeral-push era and no longer applies.
# `detail`/`list` flip this same sheet between the compact grid and ONE item's full dossier. The view lives in
# the persisted payload (not in the browser) so the operator's voice drives it: the widget has no state of its own.
def apply_action(action: str, payload: dict | None = None) -> dict:
    payload = payload or {}
    # V2-259 — WHICH sheet. It travels in the payload rather than the URL for the same reason as `task_id` in the
    # browser: the canvas sends actions to the BASE widget and puts the instance inside (`desktop.js`). Without
    # `sheet`, this continues operating on the default sheet, which keeps the change from breaking anyone.
    #
    # ...and `q` is the SAME THING under the canvas's own name, which is the whole bug of V2-540. `ctx.action`
    # stamps the instance into every payload as `q` (`desktop.js`, one place, for every widget) while this read
    # only ever looked for `sheet`, a key the canvas has never sent. So EVERY click on an instantiated sheet —
    # «Ver detalle», «choose», switching tab — was answered against the DEFAULT sheet, found nothing there and
    # came back `{ok:false}`. Reported by the operator as «el botón de ver detalle no es clic», which is exactly
    # what a working button looks like when its request lands on the wrong sheet.
    # `view_data(q)` has read the instance out of `q` since V2-259; the writer simply never followed.
    sheet = _safe_sheet(payload.get("sheet") or payload.get("q"))
    handler = ACTIONS.get(action) if isinstance(action, str) else None
    if handler is None:
        return {"ok": False, "error": f"acción «{action}» no soportada (present · append · clear · choose · detail · "
                                      f"list · tab · sources · progress · criteria · auth_done)"}
    return handler(action, payload, sheet)
