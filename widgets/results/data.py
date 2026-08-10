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
# which is exactly what the operator saw and reported ("solo veo el widget de proyectos abierto, que no tiene
# nada que ver"). A generic presentation surface has NO content of its own: with nothing pushed it is an EMPTY
# SHEET, never someone else's data.
#
# HISTORY (2026-08-09): a result was strictly FLAT — one card = one thing. That cannot express what a real
# research answer looks like: the operator asked for holiday PROPOSALS, and a proposal is a BUNDLE (this hotel +
# that ferry crossing + maybe a restaurant), each piece with its own price, photo, link and times. Flattening a
# bundle into free text loses the structure the operator wants to compare on. So an item may now carry `parts`
# (the pieces it is made of) plus, for the DRILL-DOWN, `images`/`facts` (a photo gallery and the label→value
# sheet: check-in, port, cancellation policy…). And `view`/`focus` give the sheet a SECOND PAGE: "enséñame en
# detalle la propuesta 1" switches this same widget to the full dossier of one item instead of the compact grid.
#
from .. import store

WIDGET_ID = "results"

# Fields an item may carry. Anything else pushed is dropped — the payload comes from a worker that read the open
# web, so we never let arbitrary keys through to the renderer (widget.js paints with textContent only, but the
# schema is the contract and it stays closed).
_ITEM_FIELDS = ("title", "subtitle", "price", "badge", "url", "image", "primary", "lines",
                "parts", "images", "facts", "score")
# A PART is one piece of a composite item (the hotel inside a holiday plan, the ferry, the restaurant). Same
# closed-schema discipline; `kind` is the piece's role ("Hotel", "Ferry", "Restaurante") so the card can label it.
_PART_FIELDS = ("kind", "title", "subtitle", "price", "url", "image", "lines", "facts")

_MAX_ITEMS = 60          # a report the operator can actually read; widget.js renders the first 24 and says how many more
# `lines` used to cap at 4 — fine for a spec-sheet bullet list, but a real request ("show me the lyrics to X") needs
# a whole song's worth of text in ONE item's body (2026-08-03). Raised so a full block of text fits; still bounded
# so a worker can't paste an entire scraped page into a card.
_MAX_LINES = 80
_MAX_LINE_CHARS = 300
_MAX_PARTS = 6           # a plan is a handful of pieces (hotel+ferry+restaurante), never a list in disguise
_MAX_PART_LINES = 20
_MAX_IMAGES = 12         # the detail page's photo gallery
_MAX_FACTS = 30          # label→value sheet (check-in, puerto, política de cancelación…)
_MAX_FACT_CHARS = 200


# ── CONTROL DE CALIDAD DE PRESENTACIÓN (2026-08-10) ───────────────────────────────────────────────────────────────
# Los presupuestos de campo y las reglas viven en `widgets/presentation.py` (compartidas por TODA superficie en
# blanco); aquí solo se aplican. Dos cosas cambian respecto a antes:
#   · el recorte va por frontera de PALABRA y se marca. El `[:200]` de antes cortó un aviso real del worker
#     («⚠️ Llevar tu cadena…») dejándolo en «⚠️ Llevar tu c»: una salvedad amputada engaña más que su ausencia.
#   · un payload que rompe la tarjeta deja RASTRO. Un prompt es una petición, no una garantía: si el título trae
#     tres ideas dentro, se registra y vuelve en la respuesta de la acción, así el worker puede corregirlo.
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
    ("¿a qué hora es el check-in?", "¿lleva desayuno?"). Written naturally as {label: value} by whoever found it,
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


def _empty() -> dict:
    return {"title": "Resultados", "subtitle": "", "items": []}


def view_data(q: str = "") -> dict:
    """The LAST result set pushed here, verbatim. Nothing pushed yet → an empty sheet (never invented content)."""
    db = store.load(WIDGET_ID, _empty())
    if not isinstance(db, dict):
        db = _empty()
    data = dict(db)
    data.setdefault("title", "Resultados")
    data["items"] = _clean_items(data.get("items"))
    if not data["items"]:
        data.setdefault("note", "Sin resultados todavía.")
        data.pop("view", None)                   # no items ⇒ there is nothing to be showing the detail OF
        data.pop("focus", None)
    return data


def _find(items: list[dict], title: str = "", index=None) -> dict | None:
    """Resolve WHICH item the operator means. By exact title, else by a forgiving contains-match, else by ordinal.
    The ordinal matters because this arrives from VOICE: "enséñame la propuesta número uno" is far more likely to
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


def ref_index() -> list[dict]:
    """The items currently ON SCREEN, so the brain can (a) let the operator pick one by talking about it ("quédate
    con la del beach club") and (b) — just as important — SEE that the sheet is empty. Before this, an open but
    blank results card was indistinguishable from a card that simply doesn't publish its items, and the brain
    answered "aquí lo tienes" over an empty screen (real session, 12:57:57).

    The hint leads with the ORDINAL because that is how the operator refers to a proposal out loud ("la número
    dos"); without it the brain had to guess which card "the second one" was."""
    out = []
    for n, it in enumerate(view_data().get("items", []), 1):
        bits = [f"#{n}"]
        if it.get("price"):
            bits.append(it["price"])
        if it.get("parts"):
            bits.append(" + ".join(p.get("kind") or p.get("title") or "" for p in it["parts"]))
        elif it.get("subtitle"):
            bits.append(it["subtitle"])
        out.append({"id": it["title"], "label": it["title"], "field": "title",
                    "hint": " · ".join(b for b in bits if b)})
    return out


def prompt_digest() -> str:
    """What is ACTUALLY on screen, compact enough to ride in every prompt while this widget is open.

    Why this exists: `ref_index()` only publishes title+hint, so the brain could name the items but knew nothing
    about them. Asked "¿el hotel de la propuesta 2 tiene wifi?" — about a result already on screen, whose own
    card says so — it had to either guess or escalate a whole new search for a fact it was already holding. That
    is the difference between a screen the agent can SEE and one it merely painted. Bounded on purpose: this is
    a digest for reasoning over, not the full dossier (that lives in the detail view)."""
    data = view_data()
    items = data.get("items") or []
    if not items:
        return "hoja VACÍA — no hay ningún resultado en pantalla todavía"
    lines = []
    if data.get("view") == "detail" and data.get("focus"):
        lines.append(f"[viendo el DETALLE de «{data['focus']}»]")
    for n, it in enumerate(items[:12], 1):
        head = f"#{n} {it.get('title','')}"
        if it.get("price"):
            head += f" — {it['price']}"
        if it.get("badge"):
            head += f" [{it['badge']}]"
        lines.append(head)
        if it.get("subtitle"):
            lines.append(f"   {it['subtitle']}")
        for p in (it.get("parts") or []):
            bit = f"   · {p.get('kind') or 'pieza'}: {p.get('title','')}"
            if p.get("price"):
                bit += f" ({p['price']})"
            lines.append(bit)
            for f in (p.get("facts") or [])[:6]:
                lines.append(f"     - {f['label']}: {f['value']}")
        for f in (it.get("facts") or [])[:8]:
            lines.append(f"   - {f['label']}: {f['value']}")
        for ln in (it.get("lines") or [])[:3]:
            lines.append(f"   {ln}")
    if len(items) > 12:
        lines.append(f"(+{len(items) - 12} resultados más en la hoja)")
    return "\n".join(lines)


# present/append/clear = how the result set is delivered. `choose` lets the operator PICK one of the shown items
# (e.g. "quiero esa"); unlike before it now PERSISTS the pick, because the list itself is persisted — the old
# comment about avoiding store.save() described the ephemeral-push era and no longer applies.
# `detail`/`list` flip this same sheet between the compact grid and ONE item's full dossier. The view lives in
# the persisted payload (not in the browser) so the operator's voice drives it: the widget has no state of its own.
def apply_action(action: str, payload: dict | None = None) -> dict:
    payload = payload or {}

    if action == "present":
        issues = _audit(payload)
        items = _clean_items(payload.get("items"))
        data = {
            "title": _clip(payload.get("title") or "Resultados", "sheet_title"),
            "subtitle": _clip(payload.get("subtitle"), "sheet_subtitle"),
            "items": items,
        }
        # `columns` se conserva como TOPE (la superficie decide el reparto por la forma del contenido, ver
        # widget.js::columnsFor), nunca como orden — un 2 adivinado dejaba 3 tarjetas ricas con una huérfana.
        cols = payload.get("columns")
        if isinstance(cols, int) and 1 <= cols <= 3:
            data["columns"] = cols
        if payload.get("choosable"):
            data["choosable"] = True
        if not items:
            data["note"] = _clip(payload.get("note") or "Sin resultados.", "sheet_subtitle")
        store.save(WIDGET_ID, data)
        return {"ok": True, "shown": len(items), "presentation": issues}

    if action == "append":
        issues = _audit(payload)
        add = _clean_items(payload.get("items"))
        if not add:
            return {"ok": False, "error": "append sin items válidos (cada item necesita al menos title)"}
        data = view_data()
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
        store.save(WIDGET_ID, data)
        return {"ok": True, "shown": len(data["items"]), "presentation": issues}

    if action == "clear":
        store.save(WIDGET_ID, _empty())
        return {"ok": True, "shown": 0}

    if action == "choose":
        title = str(payload.get("title", "")).strip()
        if not title:
            return {"ok": False, "error": "choose necesita el title EXACTO del item"}
        data = view_data()
        data["chosen"] = title
        store.save(WIDGET_ID, data)
        return {"ok": True, "chosen": title}

    if action == "detail":
        data = view_data()
        it = _find(data.get("items") or [], str(payload.get("title", "")), payload.get("index"))
        if not it:
            return {"ok": False, "error": "no encuentro ese resultado en la hoja (pasa el title o index 1-based)"}
        data["view"] = "detail"
        data["focus"] = it["title"]
        store.save(WIDGET_ID, data)
        return {"ok": True, "detail": it["title"]}

    if action == "list":
        data = view_data()
        data.pop("view", None)
        data.pop("focus", None)
        store.save(WIDGET_ID, data)
        return {"ok": True, "view": "list"}

    return {"ok": False, "error": f"acción «{action}» no soportada (present · append · clear · choose · detail · list)"}
