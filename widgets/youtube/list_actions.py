"""What each QUEUE-EDITING action does — remove, move, sort, filter, name, clear (split from `actions.py`)."""
from __future__ import annotations

from . import data as _d
from . import result_refs as _rr


def _a_remove(action, p, db) -> dict:
    lst = db.get("list") or []
    # V2-756 — «Bórrame los tres últimos de la cola» removed ONE (live session 74be8e9a). The reply
    # even said «quito el 4, el 5 y el 6», because the model had understood perfectly; there was no
    # declared way to say it, and one action per turn is the rule. He spent seventy seconds and three
    # complaints getting three rows deleted, ending on «Eso es absurdo, no estás entendiendo la
    # tarea.» And the paid verdict, with nothing better to reach for, answered `clear_list` at 0.56 —
    # the action that empties the WHOLE queue (V2-742's pattern: the nearest declared action does
    # something worse). `add_results` has taken «1,3» since V2-632; its mirror just never did.
    many = _d._index_list(p.get("items"), len(lst))
    if many:
        gone, pos = [], int(db.get("pos", -1))
        for i in sorted(many, reverse=True):          # highest first: an earlier pop shifts the rest
            gone.append((lst.pop(i) or {}).get("title"))
            if i <= pos:
                pos -= 1
        db["pos"] = pos
        _d.store.save(_d.WID, db)
        return {"ok": True, "removed": [t for t in gone if t][::-1], "count": len(lst)}
    idx = _d._resolve_item(lst, p.get("item"))
    if idx is None:
        return {"ok": False, "error": "item_not_found", "item": p.get("item"),
                "message": "No encuentro ese vídeo en la lista."}
    removed = lst.pop(idx)
    pos = int(db.get("pos", -1))
    # Keep `pos` meaning "last played": removing an earlier item shifts everything one left, and removing
    # the CURRENT one leaves pos pointing at the slot BEFORE the next item — so `ended`/`next` (pos+1)
    # play exactly the item that followed the removed one. Playback itself is untouched (like YouTube).
    if idx <= pos:
        db["pos"] = pos - 1
    _d.store.save(_d.WID, db)
    return {"ok": True, "removed": removed.get("title"), "count": len(lst)}


def _a_move(action, p, db) -> dict:
    from . import move_refs as _mv          # which video, which slot, and which half a refusal names (2026-10-11)
    lst = db.get("list") or []
    if not str(p.get("item") if p.get("item") is not None else "").strip():
        return _mv.refusal("missing_item")
    idx = _mv.resolve_item(lst, p.get("item"), db)
    if idx is None:
        return {"ok": False, "error": "item_not_found", "item": p.get("item"),
                "message": "No encuentro ese vídeo en la lista."}
    # «put X before Y» names the OTHER video, not a slot (video-queue use case, 2026-10-11): the anchor is resolved
    # like `item`, and the slot is computed after X leaves the list — the model had to do that arithmetic before.
    side = "before" if str(p.get("before") or "").strip() else ("after" if str(p.get("after") or "").strip() else "")
    if side:
        anchor = _mv.resolve_item(lst, p.get(side), db)
        if anchor is None:
            return {"ok": False, "error": "item_not_found", "item": p.get(side),
                    "message": "No encuentro ese vídeo en la lista."}
        if anchor == idx:
            return {"ok": False, "error": "same_item", "message": "Es el mismo vídeo: dime cuál va delante de cuál."}
        to = (anchor - 1 if anchor > idx else anchor) + (1 if side == "after" else 0)
    else:
        to, given = _mv.destination(p, len(lst))        # `to` or `position`; a number, an ordinal or an end
        if to is None:
            return _mv.refusal("bad_position" if given else "missing_position")
    if to == idx:            # nothing would change: refused, so the repair reads his sentence instead of «Done.»
        return _mv.refusal("already_there", item=lst[idx].get("title"), position=idx + 1)
    cur = lst[int(db.get("pos", -1))] if 0 <= int(db.get("pos", -1)) < len(lst) else None
    it = lst.pop(idx)
    lst.insert(to, it)
    if cur is not None:                              # pos follows the ITEM that was playing, not the slot
        db["pos"] = lst.index(cur)
    _d.store.save(_d.WID, db)
    return {"ok": True, "moved": it.get("title"), "position": to + 1, "order": [str(x.get("title") or "") for x in lst]}


def _a_sort_list(action, p, db) -> dict:
    by = str(p.get("by") or "title").strip().lower()
    if by not in ("title", "added"):
        return {"ok": False, "error": "bad_sort", "message": "Puedo ordenar por 'title' o por 'added'."}
    lst = db.get("list") or []
    cur = lst[int(db.get("pos", -1))] if 0 <= int(db.get("pos", -1)) < len(lst) else None
    if by == "title":
        lst.sort(key=lambda it: _d._norm(it.get("title")))
    else:
        lst.sort(key=lambda it: (int(it.get("added_at") or 0), int(it.get("added_seq") or 0)))
    if cur is not None:
        db["pos"] = lst.index(cur)
    _d.store.save(_d.WID, db)
    return {"ok": True, "by": by, "count": len(lst)}


def _a_filter_list(action, p, db) -> dict:
    # Display-only: the widget shows the rows matching the text; the list itself never changes.
    db["list_filter"] = str(p.get("q") or p.get("query") or "").strip()
    _d.store.save(_d.WID, db)
    return {"ok": True, "filter": db["list_filter"]}


def _a_name_list(action, p, db) -> dict:
    # Naming is not renaming ANOTHER list: this player has exactly ONE queue, so the name is a field of
    # the card, not an entity. Empty clears it back to the generic title — the same «empty = remove» that
    # `filter_list` already uses, so two list actions do not disagree about what an empty payload means.
    nombre = str(p.get("name") or p.get("title") or p.get("item") or "").strip()[:80]
    db["list_name"] = nombre
    _d.store.save(_d.WID, db)
    return {"ok": True, "name": nombre, "count": len(db.get("list") or [])}


def _a_clear_list(action, p, db) -> dict:
    # Empties the LIST only: whatever is playing keeps playing (voice «empty the list» must not cut the
    # video — close is the action that stops playback).
    if not db.get("list") and db.get("search_results"):
        return _rr.nothing_queued()                  # «Hecho» over an empty queue hid the add he asked for
    db["list"] = []
    db["pos"] = -1
    _d.store.save(_d.WID, db)
    return {"ok": True, "count": 0}
