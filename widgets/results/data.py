#
# results widget — backend. INTENTIONALLY does no searching of its own: it is the GENERIC PRESENTATION SURFACE of
# zaelar. Whoever DID the work (a Brain Worker that searched the web, the navegador, the FlashBrain) hands it a
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
from .. import store

WIDGET_ID = "results"

# ── UNA HOJA POR ENCARGO (V2-259) ─────────────────────────────────────────────────────────────────────────────
# Petición del operador, literal: «si tenemos un widget de results abierto, búsqueda terminada, y lanzamos otra,
# se abre un widget nuevo. Con esta regla no cometeremos errores de borrar búsquedas». El borrado que teme estaba
# EN EL CÓDIGO: `begin_task(fresh=True)` estrenaba la hoja —título nuevo, sin resultados ni historial— en cuanto
# llegaba el encargo siguiente. Con instancias, ESTRENAR deja de significar BORRAR: una hoja nueva es una clave
# nueva y la anterior sigue donde estaba.
#
# La instancia es el ENCARGO, no el navegador. Dos navegadores del mismo encargo caen en la misma hoja (V2-257:
# la hoja guarda los hallazgos vengan del navegador que vengan); dos encargos son dos hojas.
#
# La clave VACÍA sigue siendo `results` a pelo, y eso es deliberado: es la hoja que ya existe en disco, así que no
# hay que migrar nada ni queda un linaje huérfano compitiendo con otro (la trampa de V2-242, donde `weather:soria`
# y `meteo-soria:weather:soria` convivieron los dos con `valid=1`). Lo que sí hay que vigilar —y tiene su test— es
# que ningún ESCRITOR se quede sin saber su hoja: escribiría en la de nadie mientras el operador mira la suya.
_INSTANCE_SEP = "--"          # `widgets/store._safe_id` solo deja [A-Za-z0-9_-]: «::» no sobreviviría al disco
_MAX_SHEETS = 8               # techo de hojas instanciadas guardadas; ver `prune_sheets()`


def _safe_sheet(sheet) -> str:
    return "".join(c for c in str(sheet or "").strip() if c.isalnum() or c in "-_")[:64]


def sheet_key(sheet: str = "") -> str:
    """Clave de almacén de UNA hoja. Sin instancia → la de siempre, byte por byte. `results::X` ES `X`."""
    s = _safe_sheet(str(sheet or "").removeprefix(f"{WIDGET_ID}::"))   # V2-439: sin esto la clave NO existe
    return WIDGET_ID if not s else f"{WIDGET_ID}{_INSTANCE_SEP}{s}"


def sheets() -> list[str]:
    """Las hojas que EXISTEN en disco, la de siempre primero y las instanciadas por orden de escritura (la más
    reciente al final). Se lee del almacén y no de una lista en memoria a propósito: la hoja persiste entre
    reinicios (V2-233) y una lista en RAM diría «no hay ninguna» justo después de arrancar."""
    out: list[str] = []
    try:
        import os
        base = store.DATA_DIR
        pref = WIDGET_ID + _INSTANCE_SEP
        rows = []
        for name in os.listdir(base):
            if not name.startswith(pref):
                continue
            f = os.path.join(base, name, "state.json")
            if os.path.exists(f):
                rows.append((os.path.getmtime(f), name[len(pref):]))
        rows.sort()
        out = [sid for _, sid in rows]
    except Exception:  # noqa: BLE001
        return [""] if store.exists(WIDGET_ID) else []
    if store.exists(WIDGET_ID):
        out.insert(0, "")
    return out


def prune_sheets(keep: int = _MAX_SHEETS) -> int:
    """Techo de hojas guardadas. La hoja PERSISTE a propósito, así que N instancias crecen sin fin; se conservan
    las `keep` más recientes y la de siempre (que no es de ningún encargo y no le toca a nadie borrarla).
    Devuelve cuántas se tiraron, para que el recorte se pueda CONTAR en vez de descubrirse."""
    inst = [s for s in sheets() if s]
    dropped = 0
    for sid in inst[:max(0, len(inst) - max(1, keep))]:
        try:
            if store.delete(sheet_key(sid)):
                dropped += 1
        except Exception:  # noqa: BLE001
            pass
    return dropped


def instance_id(sheet: str = "") -> str:
    """Id de TARJETA en el canvas (`results::<corr>`), que usa «::» — el separador del canvas, no el del disco."""
    s = _safe_sheet(sheet)
    return WIDGET_ID if not s else f"{WIDGET_ID}::{s}"

# Fields an item may carry. Anything else pushed is dropped — the payload comes from a worker that read the open
# web, so we never let arbitrary keys through to the renderer (widget.js paints with textContent only, but the
# schema is the contract and it stays closed).
_ITEM_FIELDS = ("title", "subtitle", "price", "badge", "url", "image", "primary", "lines",
                "parts", "images", "facts", "score", "blocks")
# A PART is one piece of a composite item (the hotel inside a holiday plan, the ferry, the restaurant). Same
# closed-schema discipline; `kind` is the piece's role ("Hotel", "Ferry", "Restaurante") so the card can label it.
_PART_FIELDS = ("kind", "title", "subtitle", "price", "url", "image", "lines", "facts")

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

_MAX_ITEMS = 60          # a report the operator can actually read; widget.js renders the first 24 and says how many more
# `lines` used to cap at 4 — fine for a spec-sheet bullet list, but a real request ("show me the lyrics to X") needs
# a whole song's worth of text in ONE item's body (2026-08-03). Raised so a full block of text fits; still bounded
# so a worker can't paste an entire scraped page into a card.
_MAX_LINES = 80
_MAX_LINE_CHARS = 300
_MAX_PARTS = 6           # a plan is a handful of pieces (hotel+ferry+restaurant), never a list in disguise
_MAX_PART_LINES = 20
_MAX_IMAGES = 12         # the detail page's photo gallery
_MAX_FACTS = 30          # label→value sheet (check-in, port, cancellation policy...)
_MAX_FACT_CHARS = 200

# ── THE TABS THAT ARE NOT THE LIST ───────────────────────────────────────────────────────────────────────────
# «process» ES una pestaña como las demás: si el operador la elige, su elección se PERSISTE igual que las
# otras. Faltaba de esta tupla y el clic volvía `{"ok": false, "error": "pestaña «process» desconocida"}` —
# la pestaña se pintaba (el widget la conmuta en el acto) y al siguiente refresco de datos, que durante un
# encargo vivo llega con cada fase, el derivado se lo llevaba de vuelta a Resultados. Un clic que no se
# guarda no falla con ruido: falla arrancándole al operador de donde había decidido mirar (V2-227 C).
_TABS = ("process", "results", "summary", "sources", "criteria")

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
    for label, value in items:
        if label in (None, "") or value in (None, ""):
            continue
        out.append({"label": str(label)[:80], "value": str(value)[:_MAX_FACT_CHARS]})
        if len(out) >= _MAX_FACTS:
            break
    return out


def _clean_lines(raw, cap: int) -> list[str]:
    if isinstance(raw, (list, tuple)):
        return [str(x)[:_MAX_LINE_CHARS] for x in raw if x not in (None, "")][:cap]
    if raw:
        return [str(raw)[:_MAX_LINE_CHARS]]
    return []


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
    if not isinstance(raw, (list, tuple)):
        return []
    out = []
    for r in raw:
        b = _clean_block(r, depth)
        if b:
            out.append(b)
        if len(out) >= _MAX_BLOCKS:
            break
    return out


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


# El PROCESO en vivo vive en `widgets/results/live.py` (V2-296): todo lo de allí es derivado del registro del
# dispatcher, y lo de aquí es el contenido que la hoja posee. Se re-exporta porque es una mudanza, no un cambio
# de interfaz — los tests y `view_data` siguen llamándolos por su nombre de siempre.
from widgets.results.live import (  # noqa: E402,F401 — re-export
    _MAX_PHASES, _MAX_PHASE_CHARS, _clean_phases, _harvest, _progress)


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
    if not data["items"]:
        data.setdefault("note", "Sin resultados todavía.")
        data.pop("view", None)                   # no items ⇒ there is nothing to be showing the detail OF
        data.pop("focus", None)
    stored = _clean_phases(data.get("process"))
    if stored:
        data["process"] = stored
    else:
        data.pop("process", None)            # sin historial, la hoja en blanco sigue en blanco
    data["counts"] = _counts(data)
    data["progress"] = _progress(data, _safe_sheet(q))
    data["harvest"] = _harvest(data, _safe_sheet(q))
    return data


def _save(data: dict, sheet: str = "") -> None:
    """Persist WITHOUT derived fields: `counts` is recalculated on read, and storing it would make it stale as soon as
    anything else changes (an old number on screen is worse than no number)."""
    d = dict(data)
    d.pop("counts", None)
    d.pop("progress", None)                  # derivado del registro vivo: guardarlo es congelar un «Trabajando…»
    for k in ("sources", "summary", "criteria"):
        if not d.get(k):
            d.pop(k, None)                       # remove empty sections: the blank sheet remains blank
    store.save(sheet_key(sheet), d)


def _find(items: list[dict], title: str = "", index=None) -> dict | None:
    """Resolve WHICH item the operator means. By exact title, else by a forgiving contains-match, else by ordinal.
    The ordinal matters because this arrives from VOICE: "show me proposal number one" is far more likely to
    survive STT intact than a hotel's full commercial name, so the caller may pass index=1 instead of a title."""
    if isinstance(index, (int, float)) and not isinstance(index, bool):
        i = int(index)
        if 1 <= i <= len(items):                 # 1-based: the operator counts from one, not from zero
            return items[i - 1]
    t = (title or "").strip().lower()
    if not t:
        return None
    for it in items:
        if (it.get("title") or "").strip().lower() == t:
            return it
    for it in items:
        if t in (it.get("title") or "").strip().lower():
            return it
    return None


# ── EL ENCARGO ABRE Y CIERRA LA HOJA (V2-227 ámbito C · extraído a `widgets/results/lifecycle.py`, V2-530) ────
# Las tres puertas que el dispatcher usa para que el operador VEA el trabajo mientras pasa. No son acciones del
# vocabulario de `apply_action`: nadie las pide desde un prompt, las dispara el ciclo de vida del encargo —
# meterlas ahí las pondría al alcance de un worker, que es justo quien no debe decidir cuándo se estrena la hoja.
# Se re-exportan aquí —misma mudanza y mismo gesto que `live.py` (V2-296)— porque este módulo ES el contrato de
# la hoja para todo el que la usa: los llamantes siguen diciendo `data.begin_task`.
from widgets.results.lifecycle import (  # noqa: E402,F401 — re-export
    begin_task, end_task, rename_task)


def _sheets_for_brain(sheet) -> list[str]:
    """QUÉ hojas ve el cerebro. Con `sheet` dado, esa; sin él, TODAS las que existen.

    Que el defecto sea «todas» es la decisión, y su contraria es la que falla callando: con dos encargos vivos,
    leer solo una dejaría al turno contestando con seguridad sobre la hoja equivocada —«¿el hotel de la
    propuesta 2 tiene wifi?» resuelto contra la búsqueda del fontanero— sin que nada indicara que había otra.
    Es la misma clase de mentira que V2-257 quitó de la tarjeta: no una verdad más pequeña, otra y falsa.
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

    V2-259 — con varias hojas abiertas cada referencia dice DE CUÁL es. El ordinal solo desambigua dentro de una
    hoja: «la número dos» con dos búsquedas en pantalla son dos cosas distintas, y sin el encargo delante el turno
    elegiría una en silencio.
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
                bits.append(f"de «{titulo}»")
            if it.get("price"):
                bits.append(it["price"])
            if it.get("parts"):
                bits.append(" + ".join(p.get("kind") or p.get("title") or "" for p in it["parts"]))
            elif it.get("subtitle"):
                bits.append(it["subtitle"])
            out.append({"id": it["title"], "label": it["title"], "field": "title",
                        "sheet": sid, "hint": " · ".join(b for b in bits if b)})
    return out


# V2-287 — el digest del prompt vive en su propio módulo (`digest.py`): son funciones puras de un dict de
# hoja, sin store y sin escrituras. Aquí se quedan los dos nombres que SÍ necesitan el almacén —qué hojas
# existen y qué hay dentro—, y `_digest_head`/`_digest_one` siguen re-exportados porque son el contrato que
# ya usan los tests de la superficie.
from . import digest as _digest                                                              # noqa: E402
from .digest import head as _digest_head, one as _digest_one, _MAX_HEAD_CHARS, _MAX_HEAD_ITEM  # noqa: E402,F401


def prompt_digest(sheet=None) -> str:
    """What is ACTUALLY on screen, compact enough to ride in every prompt while this widget is open.

    Why this exists: `ref_index()` only publishes title+hint, so the brain could name the items but knew nothing
    about them. Asked "does the hotel in proposal 2 have wifi?" — about a result already on screen, whose own
    card says so — it had to either guess or escalate a whole new search for a fact it was already holding. That
    is the difference between a screen the agent can SEE and one it merely painted. Bounded on purpose: this is
    a digest for reasoning over, not the full dossier (that lives in the detail view).

    V2-259 — con varias hojas se recorren TODAS y cada bloque se abre con el encargo al que pertenece. La
    alternativa (quedarse con una) no avisa de nada: el turno contestaría con seguridad sobre la búsqueda que no
    era, que es la misma clase de mentira que V2-257 quitó de la tarjeta. El techo de items es POR HOJA.
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


# present/append/clear = how the result set is delivered. `choose` lets the operator PICK one of the shown items
# (e.g. "quiero esa"); unlike before it now PERSISTS the pick, because the list itself is persisted — the old
# comment about avoiding store.save() described the ephemeral-push era and no longer applies.
# `detail`/`list` flip this same sheet between the compact grid and ONE item's full dossier. The view lives in
# the persisted payload (not in the browser) so the operator's voice drives it: the widget has no state of its own.
def apply_action(action: str, payload: dict | None = None) -> dict:
    payload = payload or {}
    # V2-259 — a QUÉ hoja. Viaja en el payload y no en la URL por la misma razón que `task_id` en el navegador:
    # el canvas manda las acciones al widget BASE y mete la instancia dentro (`desktop.js`). Sin `sheet` esto
    # sigue operando la hoja de siempre, que es lo que hace que el cambio no rompa a nadie.
    sheet = _safe_sheet(payload.get("sheet"))

    if action == "present":
        issues = _audit(payload)
        items = _clean_items(payload.get("items"))
        prev = view_data(sheet)
        data = {
            "title": _clip(payload.get("title") or "Resultados", "sheet_title"),
            "subtitle": _clip(payload.get("subtitle"), "sheet_subtitle"),
            "items": items,
        }
        # The OTHER tabs SURVIVE a `present`. During long work there are several `present`s (provisional → final), and
        # deleting sources and summary already reported on each one would lose data that took minutes of browsing.
        # They are emptied by `clear`, or at the start of a NEW investigation (`criteria` with another objective) —
        # two explicit moments, not a side effect.
        for k in ("sources", "summary", "criteria"):
            if prev.get(k):
                data[k] = prev[k]
        if prev.get("tab") in _TABS:
            data["tab"] = prev["tab"]
        # `columns` is preserved as a CAP (the surface decides distribution from content shape, see
        # widget.js::columnsFor), never as an order — a guessed 2 left 3 rich cards with one orphan.
        cols = payload.get("columns")
        if isinstance(cols, int) and 1 <= cols <= 3:
            data["columns"] = cols
        if payload.get("choosable"):
            data["choosable"] = True
        if not items:
            data["note"] = _clip(payload.get("note") or "Sin resultados.", "sheet_subtitle")
        # A `present` may also deliver the other sections (delivering everything at once is one less round trip for
        # the worker). They are MERGED over existing data, not blindly replaced.
        _merge_sections(data, payload)
        _save(data, sheet)
        return {"ok": True, "shown": len(items), "presentation": issues}

    if action == "append":
        issues = _audit(payload)
        add = _clean_items(payload.get("items"))
        if not add:
            return {"ok": False, "error": "append sin items válidos (cada item necesita al menos title)"}
        data = view_data(sheet)
        data.pop("note", None)
        seen = {(i.get("title"), i.get("url")) for i in data["items"]}
        for it in add:
            key = (it.get("title"), it.get("url"))
            if key not in seen:               # same title+url twice = the same finding, not a second result
                seen.add(key)
                data["items"].append(it)
        data["items"] = data["items"][:_MAX_ITEMS]
        if payload.get("title"):
            data["title"] = _clip(payload["title"], "sheet_title")
        if payload.get("subtitle"):
            data["subtitle"] = _clip(payload["subtitle"], "sheet_subtitle")
        _merge_sections(data, payload)
        _save(data, sheet)
        return {"ok": True, "shown": len(data["items"]), "presentation": issues}

    if action == "clear":
        store.save(sheet_key(sheet), _empty())
        return {"ok": True, "shown": 0}

    if action == "choose":
        title = str(payload.get("title", "")).strip()
        if not title:
            return {"ok": False, "error": "choose necesita el title EXACTO del item"}
        data = view_data(sheet)
        data["chosen"] = title
        _save(data, sheet)
        return {"ok": True, "chosen": title}

    if action == "detail":
        data = view_data(sheet)
        it = _find(data.get("items") or [], str(payload.get("title", "")), payload.get("index"))
        if not it:
            return {"ok": False, "error": "no encuentro ese resultado en la hoja (pasa el title o index 1-based)"}
        data["view"] = "detail"
        data["focus"] = it["title"]
        data["tab"] = "results"                  # opening a record means returning to the list, not staying on sources
        _save(data, sheet)
        return {"ok": True, "detail": it["title"]}

    if action == "list":
        data = view_data(sheet)
        data.pop("view", None)
        data.pop("focus", None)
        _save(data, sheet)
        return {"ok": True, "view": "list"}

    # ── THE OTHER THREE TABS ─────────────────────────────────────────────────────────────────────────────────
    if action == "tab":
        tab = str(payload.get("tab") or payload.get("name") or "").strip().lower()
        tab = _TAB_ALIASES.get(tab, tab)
        if tab not in _TABS:
            return {"ok": False,
                    "error": f"pestaña «{tab}» desconocida (process · results · summary · sources · criteria)"}
        data = view_data(sheet)
        data["tab"] = tab
        if tab != "results":
            data.pop("view", None)               # detail is a RESULTS page: leaving the tab closes it
            data.pop("focus", None)
        _save(data, sheet)
        return {"ok": True, "tab": tab}

    if action == "sources":
        add = _clean_sources(payload.get("sources") if payload.get("sources") is not None else payload)
        if not add:
            return {"ok": False, "error": "sources necesita al menos {name|url} por fuente"}
        data = view_data(sheet)
        cur = data.get("sources") or []
        for s in add:
            # UPSERT: a source is reported several times during work ("entering..." → "50 results, capped there").
            # If each report created a row, the tab would be a log instead of state.
            key = (s.get("url") or "").strip().lower() or (s.get("name") or "").strip().lower()
            hit = next((c for c in cur
                        if ((c.get("url") or "").strip().lower() or (c.get("name") or "").strip().lower()) == key),
                       None)
            if hit:
                hit.update(s)
            else:
                cur.append(s)
        data["sources"] = cur[:_MAX_SOURCES]
        _save(data, sheet)
        return {"ok": True, "sources": len(data["sources"])}

    if action == "progress":
        upd = _clean_summary(payload.get("summary") if isinstance(payload.get("summary"), dict) else payload)
        if not upd:
            return {"ok": False, "error": "progress necesita al menos state, explored, selected, note o steps"}
        data = view_data(sheet)
        cur = dict(data.get("summary") or {})
        steps = list(cur.get("steps") or [])
        new_steps = upd.pop("steps", [])
        for st in new_steps:
            if not steps or steps[-1] != st:     # the same repeated milestone is not progress
                steps.append(st)
        cur.update(upd)
        if steps:
            cur["steps"] = steps[-_MAX_STEPS:]
        data["summary"] = cur
        _save(data, sheet)
        return {"ok": True, "summary": cur}

    if action == "criteria":
        upd = _clean_criteria(payload.get("criteria") if isinstance(payload.get("criteria"), dict) else payload)
        if not upd:
            return {"ok": False, "error": "criteria necesita goal y/o listas hard/soft/assumed/quality_bar/changes"}
        data = view_data(sheet)
        cur = dict(data.get("criteria") or {})
        # Is this ANOTHER investigation? The objective is the task signature: if it changes, what is on screen belongs
        # to the previous search and misleads (the operator already got a stale sheet once). ROUND 2 keeps the
        # objective, so "keep searching" does not delete anything. `reset:false` disables this for fine corrections.
        new_goal = (upd.get("goal") or "").strip().lower()
        old_goal = (cur.get("goal") or "").strip().lower()
        fresh = bool(new_goal and old_goal and new_goal != old_goal)
        if payload.get("reset") is not None:
            fresh = bool(payload.get("reset"))
        if fresh:
            data = _empty()
            # CLIPPED: the brief `goal` is a self-contained paragraph ("...and report each consulted source's state"),
            # not a headline. Placed raw as the sheet title, it took five lines before showing anything. The full text
            # remains complete in the CRITERIA tab, which is where it belongs.
            data["title"] = _clip(upd.get("goal") or "Resultados", "sheet_title") or "Resultados"
            cur = {}
        cur.update(upd)
        for k in _CRIT_LISTS:                    # lists are REPLACED except `changes`, which accumulates
            if k == "changes":
                continue
            if k in upd:
                cur[k] = upd[k]
        if "changes" in upd:
            acc = list((data.get("criteria") or {}).get("changes") or []) if not fresh else []
            for ch in upd["changes"]:
                if ch not in acc:
                    acc.append(ch)
            cur["changes"] = acc[-_MAX_CRIT:]
        data["criteria"] = cur
        _save(data, sheet)
        return {"ok": True, "criteria": cur, "reset": fresh}

    return {"ok": False, "error": f"acción «{action}» no soportada (present · append · clear · choose · detail · "
                                  f"list · tab · sources · progress · criteria)"}
