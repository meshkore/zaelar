"""What each result-sheet action does, one function per action; `data.ACTIONS` maps the names to them (V2-778 F1-12,
2026-10-01).

Moved out of `widgets/results/data.py`'s `apply_action` if-chain with no behaviour change: each body is the branch
it was, and every module-level name of `data` it reads is read through it (`_d.<name>`), so a patch on `data`
still governs every call.
"""
from __future__ import annotations

from nucleo.turn import first_rows_notice as _first_rows
from search import candidacy as _cand

from . import category_gate as _gate

from . import data as _d
from . import hard_checks as _hard


def _file_pages(data: dict, pages: list[dict]) -> dict:
    """V2-782 — pages leave the list for the Sources tab, and the reply SAYS which and why (see `search.candidacy`).

    Every door into the sheet ends here, so the rule that a ranking article is a SOURCE and not a candidate is applied
    once, for the worker's own `present`, the browser's `append`, a web search's leads and a network agent's rows alike.
    A criterion no row can show is said missing in the same reply, so the worker's report says what it did NOT find."""
    extra: dict = {}
    if pages:
        _d._merge_sections(data, {"sources": _cand.as_sources(pages)})
        extra["not_candidates"] = [{"title": p["title"], "why": p["why"]} for p in pages]
        extra["note_for_worker"] = _cand.note_for_worker(pages, len(data.get("items") or []))
    gap = _cand.unshown_criteria(data.get("items") or [], data.get("criteria") or {})
    if gap:
        extra["criteria_unshown"] = gap
        extra["note_for_worker"] = (extra.get("note_for_worker", "") + " No row carries any datum (price, rating, "
                                    "phone, fact) for: " + " · ".join(gap) + ". In your report say what you did "
                                    "NOT find; never present these rows as meeting it.").strip()
    _hard.file(data, extra)        # each hard requirement is a column every row carries (yes · no · «?»)
    return extra


def _merge_notes(off: dict, extra: dict) -> dict:
    """The category gate's reply joined to the pages' one: both notes reach the worker."""
    if not off:
        return extra
    note = " ".join(x for x in (off.get("note_for_worker"), extra.get("note_for_worker")) if x)
    return {**extra, **off, "note_for_worker": note}


def _a_present(action, payload, sheet) -> dict:
    issues = _d._audit(payload)
    prev = _d.view_data(sheet)
    # A `present` that carries NO `items` key re-shows the rows already there (demo pass 132, S1: «show me» was
    # repaired into `present {tab: results}` and the four monitors were replaced by nothing — S3 then had no row
    # to open). An explicit `items: []` is still a search that found nothing, and still empties the sheet.
    if "items" not in payload and prev.get("items"):
        payload = {"items": prev["items"], "title": prev.get("title"), "subtitle": prev.get("subtitle"), **payload}
    items, pages = _cand.split(_d._clean_items(payload.get("items")))
    data = {
        "title": _d._clip(payload.get("title") or _d.default_title(), "sheet_title"),
        "subtitle": _d._clip(payload.get("subtitle"), "sheet_subtitle"),
        "items": items,
    }
    # The OTHER tabs SURVIVE a `present` (provisional → final presents must not lose minutes of browsing; the final
    # one is when `rejected` is most complete). `clear` or a NEW investigation empties them, never a side effect.
    for k in ("sources", "summary", "criteria", "rejected", "errand"):    # `errand`: who owns the shared sheet (V2-831)
        if prev.get(k):
            data[k] = prev[k]
    _gate.keep_asked(data, prev, payload)
    items, off = _gate.gate(data, items, payload)      # V2-782 T3.3: another category is not a candidate
    data["items"] = items
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
        data["note"] = _d._clip(payload.get("note") or _d.note_text("note_none", "No results."), "sheet_subtitle")
    # A `present` may also deliver the other sections (delivering everything at once is one less round trip for
    # the worker). They are MERGED over existing data, not blindly replaced.
    _d._merge_sections(data, payload)
    extra = _file_pages(data, pages)
    _d._save(data, sheet)
    _first_rows.landed(sheet, items)                   # his errand's first backed rows are told to him, once
    return {"ok": True, "shown": len(items), "presentation": issues, **_merge_notes(off, extra)}


def _a_append(action, payload, sheet) -> dict:
    issues = _d._audit(payload)
    add = _d._clean_items(payload.get("items"))
    if not add:
        return {"ok": False, "error": "append has no valid items (each item needs at least a title)"}
    data = _d.view_data(sheet)
    add, pages = _cand.split(add, prior=data["items"])
    _gate.keep_asked(data, data, payload)
    add, off = _gate.gate(data, add, payload, prior=data["items"])   # V2-782 T3.3: not a candidate, not a copy
    if add:
        data.pop("note", None)
    seen = {(i.get("title"), i.get("url")) for i in data["items"]}
    for it in add:
        key = (it.get("title"), it.get("url"))
        if key not in seen:               # same title+url twice = the same finding, not a second result
            seen.add(key)
            data["items"].append(it)
        else:                             # …but the row sent again may carry what the worker verified on it
            _hard.merge_into(data["items"], it)
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
    extra = _file_pages(data, pages)
    _d._save(data, sheet)
    _first_rows.landed(sheet, data["items"])           # his errand's first backed rows are told to him, once
    return {"ok": True, "shown": len(data["items"]), "presentation": issues, **_merge_notes(off, extra)}


def _a_clear(action, payload, sheet) -> dict:
    _d.store.save(_d.sheet_key(sheet), _d._empty())
    return {"ok": True, "shown": 0}


def _a_choose(action, payload, sheet) -> dict:
    title = str(payload.get("title", "")).strip()
    if not title:
        return {"ok": False, "error": "choose needs the item's EXACT title"}
    data = _d.view_data(sheet)
    data["chosen"] = title
    _d._save(data, sheet)
    return {"ok": True, "chosen": title}


def _a_detail(action, payload, sheet) -> dict:
    data = _d.view_data(sheet)
    it = _d._find(data.get("items") or [], _d._named(payload), payload.get("index"))
    # a name that arrived in the index slot is a name too (search-buy-used-car ES, 2026-10-11: {"index": "Fiat Tipo"}
    # against the empty base sheet never reached the errand's instance, and the reply said the row did not exist)
    _idx = payload.get("index")
    ref = _d._named(payload) or (_idx.strip() if isinstance(_idx, str) and not _idx.strip().isdigit() else "")
    if not it and ref and not (payload.get("sheet") or payload.get("q")):
        # Demo pass 107, S3: the call named no sheet, the base had no such row and the errand's instance did.
        hits = [(s, f) for s in _d.sheets() if s != sheet
                for f in [_d._find(_d.view_data(s).get("items") or [], ref, None)] if f]
        if len(hits) == 1:
            sheet, it = hits[0]
            data = _d.view_data(sheet)
    if not it:
        # `error` is the model's hint (English, internal); what HE hears is the pack's line, in his language (V2-831 R9)
        return {"ok": False, "error": "no such row on the sheet (pass its title, or a 1-based index)",
                "message": _d.note_text("refusal_no_row", ""), "say": "widgets.results.refusal_no_row"}
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
    # V2-591 — scrolling is CARD CHROME: the server only stores a witnessed REQUEST (counter + expiry) and widget.js
    # asks its host (ctx.scroll), the road a wheel gesture takes.
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
    if tab == "process":
        return _a_process_panel()
    if tab not in _d._TABS:
        return {"ok": False,
                "error": f"pestaña «{tab}» desconocida (results · summary · sources · criteria)"}
    data = _d.view_data(sheet)
    data["tab"] = tab
    if tab != "results":
        data.pop("view", None)               # detail is a RESULTS page: leaving the tab closes it
        data.pop("focus", None)
    _d._save(data, sheet)
    return {"ok": True, "tab": tab}


def _a_process_panel() -> dict:
    """«Proceso» said to the sheet opens the PROCESSES PANEL (V2-822, the operator's decision 5).

    The sheet has no process tab any more: what the errand is doing lives in the running process's entry in the
    processes panel. The request still arrives as this declared action (`tab` → `process`), so the action itself
    takes him there — the same `panel` event `show_panel` emits, on «Procesos ▸ En curso» — instead of refusing and
    leaving the model to make a second call it may not make."""
    try:
        from voice.observer import emit
        emit("panel", "open", extra={"tab": "procesos", "src": "results:tab"})
    except Exception as e:  # noqa: BLE001 — an event that cannot be emitted is said, not swallowed
        return {"ok": False, "error": f"could not open the processes panel: {e}"}
    return {"ok": True, "tab": "process", "opened": "procesos",
            "note": "the processes panel is open on what is running now"}


def _a_sources(action, payload, sheet) -> dict:
    add = _d._clean_sources(payload.get("sources") if payload.get("sources") is not None else payload)
    if not add:
        return {"ok": False, "error": "sources needs at least {name|url} per source"}
    data = _d.view_data(sheet)
    cur = data.get("sources") or []
    # UPSERT: a source is reported several times during work ("entering..." → "50 results, capped there").
    # If each report created a row, the tab would be a log instead of state.
    key = lambda s: ((s.get("url") or "").strip() or (s.get("name") or "").strip()).lower()     # noqa: E731
    for s in add:
        hit = next((c for c in cur if key(c) == key(s)), None)
        hit.update(s) if hit else cur.append(s)
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
        return {"ok": False, "error": "rejected needs {title, why} per discarded candidate"}
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
        return {"ok": False, "error": "progress needs at least one of state, explored, selected, note, steps"}
    data = _d.view_data(sheet)
    cur = dict(data.get("summary") or {})
    steps = list(cur.get("steps") or [])
    for st in upd.pop("steps", []):
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
        return {"ok": False, "error": "criteria needs a goal and/or hard/soft/assumed/quality_bar/changes lists"}
    data = _d.view_data(sheet)
    cur = dict(data.get("criteria") or {})
    # Is this ANOTHER investigation? The objective is the task signature: if it changes, what is on screen belongs
    # to the previous search and misleads (the operator already got a stale sheet once). ROUND 2 keeps the
    # objective, so "keep searching" does not delete anything. `reset:false` disables this for fine corrections.
    new_goal = (upd.get("goal") or "").strip().lower()
    old_goal = (cur.get("goal") or "").strip().lower()
    fresh = bool(new_goal and old_goal and new_goal != old_goal)
    # …but only on the shared sheet. A NAMED sheet belongs to one errand (V2-276: `sheet_id_for(task_id)`), so a
    # goal that changes there is the same errand re-worded — wiping its delivered rows for a paraphrase was the
    # audit's P1-2 (V2-783). Another investigation gets another sheet; an explicit `reset` still wins.
    if fresh and sheet and data.get("items"):
        fresh = False
    if payload.get("reset") is not None:
        fresh = bool(payload.get("reset"))
    if fresh:
        data = _d._empty()
        # CLIPPED: the brief `goal` is a self-contained paragraph ("...and report each consulted source's state"),
        # not a headline. Placed raw as the sheet title, it took five lines before showing anything. The full text
        # remains complete in the CRITERIA tab, which is where it belongs.
        data["title"] = _d._clip(upd.get("goal") or _d.default_title(), "sheet_title") or _d.default_title()
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
    _open = _hard.stamp(data)              # the rows already on the sheet get the new columns too
    _d._save(data, sheet)
    off = _gate.recheck(sheet, "")              # a criterion that rules rows out applies to the rows already there
    return {"ok": True, "criteria": cur, "reset": fresh, **({"off_category": off} if off else {}),
            **({"hard_unverified": _open} if _open else {})}


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
