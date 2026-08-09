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
from .. import store

WIDGET_ID = "results"

# Fields an item may carry. Anything else pushed is dropped — the payload comes from a worker that read the open
# web, so we never let arbitrary keys through to the renderer (widget.js paints with textContent only, but the
# schema is the contract and it stays closed).
_ITEM_FIELDS = ("title", "subtitle", "price", "badge", "url", "image", "primary", "lines")
_MAX_ITEMS = 60          # a report the operator can actually read; widget.js renders the first 24 and says how many more
# `lines` used to cap at 4 — fine for a spec-sheet bullet list, but a real request ("show me the lyrics to X") needs
# a whole song's worth of text in ONE item's body (2026-08-03). Raised so a full block of text fits; still bounded
# so a worker can't paste an entire scraped page into a card.
_MAX_LINES = 80
_MAX_LINE_CHARS = 300


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
            if isinstance(v, (list, tuple)):
                it[k] = [str(x)[:_MAX_LINE_CHARS] for x in v if x not in (None, "")][:_MAX_LINES]
            elif v:
                it[k] = [str(v)[:_MAX_LINE_CHARS]]
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
    return data


def ref_index() -> list[dict]:
    """The items currently ON SCREEN, so the brain can (a) let the operator pick one by talking about it ("quédate
    con la del beach club") and (b) — just as important — SEE that the sheet is empty. Before this, an open but
    blank results card was indistinguishable from a card that simply doesn't publish its items, and the brain
    answered "aquí lo tienes" over an empty screen (real session, 12:57:57)."""
    return [{"id": it["title"], "label": it["title"], "field": "title",
             "hint": it.get("subtitle") or it.get("price") or ""}
            for it in view_data().get("items", [])]


# present/append/clear = how the result set is delivered. `choose` lets the operator PICK one of the shown items
# (e.g. "quiero esa"); unlike before it now PERSISTS the pick, because the list itself is persisted — the old
# comment about avoiding store.save() described the ephemeral-push era and no longer applies.
def apply_action(action: str, payload: dict | None = None) -> dict:
    payload = payload or {}

    if action == "present":
        items = _clean_items(payload.get("items"))
        data = {
            "title": str(payload.get("title") or "Resultados")[:120],
            "subtitle": str(payload.get("subtitle") or "")[:200],
            "items": items,
        }
        cols = payload.get("columns")
        if isinstance(cols, int) and 1 <= cols <= 3:
            data["columns"] = cols
        if payload.get("choosable"):
            data["choosable"] = True
        if not items:
            data["note"] = str(payload.get("note") or "Sin resultados.")[:200]
        store.save(WIDGET_ID, data)
        return {"ok": True, "shown": len(items)}

    if action == "append":
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
            data["title"] = str(payload["title"])[:120]
        if payload.get("subtitle"):
            data["subtitle"] = str(payload["subtitle"])[:200]
        store.save(WIDGET_ID, data)
        return {"ok": True, "shown": len(data["items"])}

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

    return {"ok": False, "error": f"acción «{action}» no soportada (present · append · clear · choose)"}
