"""What each result-sheet action does, one function per action; `data.ACTIONS` maps the names to them (V2-778 F1-12,
2026-10-01).

Moved out of `widgets/results/data.py`'s `apply_action` if-chain with no behaviour change: each body is the branch
it was, and every module-level name of `data` it reads is read through it (`_d.<name>`), so a patch on `data`
still governs every call.
"""
from __future__ import annotations

from . import data as _d


def _a_present(action, payload, sheet) -> dict:
    issues = _d._audit(payload)
    items = _d._clean_items(payload.get("items"))
    prev = _d.view_data(sheet)
    data = {
        "title": _d._clip(payload.get("title") or "Resultados", "sheet_title"),
        "subtitle": _d._clip(payload.get("subtitle"), "sheet_subtitle"),
        "items": items,
    }
    # The OTHER tabs SURVIVE a `present`. During long work there are several `present`s (provisional → final), and
    # deleting sources and summary already reported on each one would lose data that took minutes of browsing.
    # They are emptied by `clear`, or at the start of a NEW investigation (`criteria` with another objective) —
    # two explicit moments, not a side effect.
    # `rejected` survives a `present` for the same reason as the three below, and one more: the FINAL
    # present is exactly the moment a worker replaces its provisional picks, which is when the pile of
    # what it rejected is most complete and most expensive to have lost.
    for k in ("sources", "summary", "criteria", "rejected"):
        if prev.get(k):
            data[k] = prev[k]
    if prev.get("tab") in _d._TABS:
        data["tab"] = prev["tab"]
    kind = str(payload.get("kind") or "").strip().lower()
    if kind in _d._KINDS:
        data["kind"] = kind
    elif prev.get("kind") in _d._KINDS:
        data["kind"] = prev["kind"]        # a second `present` of the same hunt does not change WHAT it found
    lay = str(payload.get("layout") or "").strip().lower()
    if lay in _d._LAYOUTS:
        data["layout"] = lay
    elif prev.get("layout") in _d._LAYOUTS:
        data["layout"] = prev["layout"]    # nor does it re-shuffle a list the operator is already reading
    # `columns` is preserved as a CAP (the surface decides distribution from content shape, see
    # widget.js::columnsFor), never as an order — a guessed 2 left 3 rich cards with one orphan.
    cols = payload.get("columns")
    if isinstance(cols, int) and 1 <= cols <= 3:
        data["columns"] = cols
    if payload.get("choosable"):
        data["choosable"] = True
    if not items:
        data["note"] = _d._clip(payload.get("note") or "Sin resultados.", "sheet_subtitle")
    # A `present` may also deliver the other sections (delivering everything at once is one less round trip for
    # the worker). They are MERGED over existing data, not blindly replaced.
    _d._merge_sections(data, payload)
    _d._save(data, sheet)
    return {"ok": True, "shown": len(items), "presentation": issues}


def _a_append(action, payload, sheet) -> dict:
    issues = _d._audit(payload)
    add = _d._clean_items(payload.get("items"))
    if not add:
        return {"ok": False, "error": "append sin items válidos (cada item necesita al menos title)"}
    data = _d.view_data(sheet)
    data.pop("note", None)
    seen = {(i.get("title"), i.get("url")) for i in data["items"]}
    for it in add:
        key = (it.get("title"), it.get("url"))
        if key not in seen:               # same title+url twice = the same finding, not a second result
            seen.add(key)
            data["items"].append(it)
    data["items"] = data["items"][:_d._MAX_ITEMS]
    if payload.get("title"):
        data["title"] = _d._clip(payload["title"], "sheet_title")
    if payload.get("subtitle"):
        data["subtitle"] = _d._clip(payload["subtitle"], "sheet_subtitle")
    kind = str(payload.get("kind") or "").strip().lower()
    if kind in _d._KINDS:
        data["kind"] = kind
    lay = str(payload.get("layout") or "").strip().lower()
    if lay in _d._LAYOUTS:
        data["layout"] = lay
    _d._merge_sections(data, payload)
    _d._save(data, sheet)
    return {"ok": True, "shown": len(data["items"]), "presentation": issues}


def _a_clear(action, payload, sheet) -> dict:
    _d.store.save(_d.sheet_key(sheet), _d._empty())
    return {"ok": True, "shown": 0}


def _a_choose(action, payload, sheet) -> dict:
    title = str(payload.get("title", "")).strip()
    if not title:
        return {"ok": False, "error": "choose necesita el title EXACTO del item"}
    data = _d.view_data(sheet)
    data["chosen"] = title
    _d._save(data, sheet)
    return {"ok": True, "chosen": title}


def _a_detail(action, payload, sheet) -> dict:
    data = _d.view_data(sheet)
    it = _d._find(data.get("items") or [], _d._named(payload), payload.get("index"))
    if not it and _d._named(payload) and not (payload.get("sheet") or payload.get("q")):
        # Demo pass 107, S3: the call named no sheet, the base had no such row and the errand's instance did.
        hits = [(s, f) for s in _d.sheets() if s != sheet
                for f in [_d._find(_d.view_data(s).get("items") or [], _d._named(payload), None)] if f]
        if len(hits) == 1:
            sheet, it = hits[0]
            data = _d.view_data(sheet)
    if not it:
        return {"ok": False, "error": "no encuentro ese resultado en la hoja (pasa el title o index 1-based)"}
    data["view"] = "detail"
    data["focus"] = it["title"]
    data["tab"] = "results"                  # opening a record means returning to the list, not staying on sources
    _d._save(data, sheet)
    return {"ok": True, "detail": it["title"]}


def _a_list(action, payload, sheet) -> dict:
    data = _d.view_data(sheet)
    data.pop("view", None)
    data.pop("focus", None)
    _d._save(data, sheet)
    return {"ok": True, "view": "list"}


def _a_scroll(action, payload, sheet) -> dict:
    # V2-591 — «haz scroll en la lista» used to get a tab switch, then a re-present, then a worker set to
    # MODIFY this widget's CODE (the operator stopped it: «No, no toques nada»). Scrolling is CARD CHROME
    # (the scroller belongs to the canvas, ctx.top()'s own rule), so the server only stores a witnessed
    # REQUEST — push counter + expiry, the V2-540 pattern — and widget.js asks its host (ctx.scroll),
    # the same road a wheel gesture takes. No accent table: the payload is normalized inline.
    _raw = "".join(c for c in _d._ud.normalize("NFKD",
                   str(payload.get("where") or payload.get("to") or "").strip().lower())
                   if not _d._ud.combining(c))
    if "arrib" in _raw or "sube" in _raw or _raw == "up":
        _wh = "up"
    elif "princip" in _raw or "inicio" in _raw or _raw in ("top", "start"):
        _wh = "top"
    elif "fond" in _raw or "final" in _raw or _raw in ("bottom", "end"):
        _wh = "bottom"
    else:
        _wh = "down"                         # «haz scroll» with nothing else = keep going down
    data = _d.view_data(sheet)
    prev = data.get("scroll") or {}
    data["scroll"] = {"where": _wh, "n": int(prev.get("n", 0)) + 1, "at": _d._tm.time()}
    _d._save(data, sheet)
    return {"ok": True, "where": _wh}


# ── THE OTHER THREE TABS ─────────────────────────────────────────────────────────────────────────────────
def _a_layout(action, payload, sheet) -> dict:
    # «Compare them visually» over a sheet already on screen (demo run, 2026-09-26): the model promised to put
    # them side by side and had no way to — the template could only arrive with `present`, which re-sends
    # every item. This re-shapes what is there; the surface still owns the geometry (presentation.py rule 1).
    lay = str(payload.get("layout") or payload.get("view") or "").strip().lower()
    if lay not in _d._LAYOUTS:
        return {"ok": False, "error": "layout needs one of: tile (side by side, with photos) · row (a dense "
                                      "list) · card (photo left) · compare (composite proposals)"}
    data = _d.view_data(sheet)
    data["layout"] = lay
    data["tab"] = "results"
    data.pop("view", None)
    _d._save(data, sheet)
    return {"ok": True, "layout": lay, "items": len(data.get("items") or [])}


def _a_tab(action, payload, sheet) -> dict:
    tab = str(payload.get("tab") or payload.get("name") or "").strip().lower()
    tab = _d._TAB_ALIASES.get(tab, tab)
    if tab not in _d._TABS:
        return {"ok": False,
                "error": f"pestaña «{tab}» desconocida (process · results · summary · sources · criteria)"}
    data = _d.view_data(sheet)
    data["tab"] = tab
    if tab != "results":
        data.pop("view", None)               # detail is a RESULTS page: leaving the tab closes it
        data.pop("focus", None)
    _d._save(data, sheet)
    return {"ok": True, "tab": tab}


def _a_sources(action, payload, sheet) -> dict:
    add = _d._clean_sources(payload.get("sources") if payload.get("sources") is not None else payload)
    if not add:
        return {"ok": False, "error": "sources necesita al menos {name|url} por fuente"}
    data = _d.view_data(sheet)
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
    data["sources"] = cur[:_d._MAX_SOURCES]
    _d._save(data, sheet)
    return {"ok": True, "sources": len(data["sources"])}


def _a_rejected(action, payload, sheet) -> dict:
    # WHAT WAS LOOKED AT AND LEFT OUT, with its reason. Reported as it goes, like `sources`, because a
    # rejection is decided at the moment of rejecting and reconstructing fifty of them at the end is how
    # they stopped being reported at all. Additive and deduped on url-or-title: the same candidate seen
    # on two portals is one rejection, not two.
    add = _d._clean_rejected(payload.get("rejected") if payload.get("rejected") is not None else payload)
    if not add:
        return {"ok": False, "error": "rejected necesita {title, why} por candidato descartado"}
    data = _d.view_data(sheet)
    cur = list(data.get("rejected") or [])
    seen = {(x.get("url") or x.get("title") or "").strip().lower() for x in cur}
    for r in add:
        key = (r.get("url") or r.get("title") or "").strip().lower()
        if key and key not in seen:
            seen.add(key)
            cur.append(r)
    data["rejected"] = cur[:_d._MAX_REJECTED]
    # The COUNT and the ROWS are the same fact seen twice, so the count follows the rows rather than
    # waiting for a separate `progress` the worker may never send. It only ever goes up to the number of
    # rows we actually hold: a summary that claims 50 over a list of 3 is the discrepancy this replaces.
    summ = dict(data.get("summary") or {})
    if int(summ.get("discarded") or 0) < len(data["rejected"]):
        summ["discarded"] = len(data["rejected"])
        data["summary"] = summ
    _d._save(data, sheet)
    return {"ok": True, "rejected": len(data["rejected"])}


def _a_progress(action, payload, sheet) -> dict:
    upd = _d._clean_summary(payload.get("summary") if isinstance(payload.get("summary"), dict) else payload)
    if not upd:
        return {"ok": False, "error": "progress necesita al menos state, explored, selected, note o steps"}
    data = _d.view_data(sheet)
    cur = dict(data.get("summary") or {})
    steps = list(cur.get("steps") or [])
    new_steps = upd.pop("steps", [])
    for st in new_steps:
        if not steps or steps[-1] != st:     # the same repeated milestone is not progress
            steps.append(st)
    cur.update(upd)
    if steps:
        cur["steps"] = steps[-_d._MAX_STEPS:]
    data["summary"] = cur
    _d._save(data, sheet)
    return {"ok": True, "summary": cur}


def _a_criteria(action, payload, sheet) -> dict:
    upd = _d._clean_criteria(payload.get("criteria") if isinstance(payload.get("criteria"), dict) else payload)
    if not upd:
        return {"ok": False, "error": "criteria necesita goal y/o listas hard/soft/assumed/quality_bar/changes"}
    data = _d.view_data(sheet)
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
        data = _d._empty()
        # CLIPPED: the brief `goal` is a self-contained paragraph ("...and report each consulted source's state"),
        # not a headline. Placed raw as the sheet title, it took five lines before showing anything. The full text
        # remains complete in the CRITERIA tab, which is where it belongs.
        data["title"] = _d._clip(upd.get("goal") or "Resultados", "sheet_title") or "Resultados"
        cur = {}
    cur.update(upd)
    for k in _d._CRIT_LISTS:                    # lists are REPLACED except `changes`, which accumulates
        if k == "changes":
            continue
        if k in upd:
            cur[k] = upd[k]
    if "changes" in upd:
        acc = list((data.get("criteria") or {}).get("changes") or []) if not fresh else []
        for ch in upd["changes"]:
            if ch not in acc:
                acc.append(ch)
        cur["changes"] = acc[-_d._MAX_CRIT:]
    data["criteria"] = cur
    _d._save(data, sheet)
    return {"ok": True, "criteria": cur, "reset": fresh}


def _a_auth_done(action, payload, sheet) -> dict:
    # V2-571 — the login handoff used to live on the browser's own card; with the browser embedded in the
    # PROCESS tab, its «Ya he iniciado sesión» button lives here and is FORWARDED to the browser's owner.
    # The sheet never touches the browser itself: it enqueues into the same mailbox the navegador card used
    # (`widgets/supervisor.enqueue`), so the owner remains the only writer of its state.
    tid = str(payload.get("task_id") or "").strip()
    if not tid:
        tid = str((_d._browser({}, sheet) or {}).get("task_id") or "")
    if not tid:
        return {"ok": False, "error": "no hay ningún navegador esperando un inicio de sesión en esta hoja"}
    try:
        from widgets import supervisor
        queued = bool(supervisor.enqueue("navegador", "auth_done", {"task_id": tid}))
    except Exception:  # noqa: BLE001
        queued = False
    if not queued:
        return {"ok": False, "error": "el navegador no está activo ahora mismo — reinténtalo en un momento"}
    return {"ok": True, "task_id": tid}
