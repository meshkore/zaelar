"""What each video-player action does (load, add, search, results, tabs); `data.ACTIONS` maps the names to them
(V2-778). Every name of `data` is read through it (`_d.<name>`), so a patch on `data` still governs every call.
Queue editing lives in `list_actions.py`, playback in `player_actions.py`.
"""
from __future__ import annotations

from . import data as _d
from . import result_refs as _rr


# V2-638 — the player is where a film is WATCHED, so the two non-YouTube sources belong on this surface
# too: a file in the agent's own library, and a torrent that plays while it is still downloading.
def _a_torrent(action, p, db) -> dict:
    # `title` (no `query`/`magnet`) is how the Descargas widget's own «▶» names an id it is adopting —
    # a fallback label for the rare case metadata carries no name yet, never a search term on its own.
    r = (_d._sources.play_local(db, str(p.get("path") or p.get("file") or ""))
         if action == "play_local" else
         _d._sources.play_torrent(db, str(p.get("query") or p.get("title") or "").strip(),
                               str(p.get("magnet") or "").strip(), bool(p.get("keep")),
                               str(p.get("id") or "").strip()))
    if not r.get("ok"):
        return r
    db["list"].append(r["item"])
    return _d._play_pos(db, len(db["list"]) - 1, "play")


def _a_load(action, p, db) -> dict:
    had_video = bool(db.get("videoId"))
    raw = str(p.get("url") or p.get("videoId") or "").strip()
    vid = _d._extract_id(raw)
    # V2-634 — provenance decides what a playback block may do (availability.py); internal swaps pass
    # pick:"ours" so re-loading through this branch never claims the operator's authorship.
    explicit = bool(vid) and str(p.get("pick") or "") != "ours"
    title = str(p.get("title") or "").strip()
    channel, published, latest = "", "", False
    if vid and not title:
        # Live, 2026-09-29: a bare `watch?v=` link played fine and the card's title was the URL itself. The
        # link names the video; the public oembed endpoint names it back (fail-open to the URL, as `add`).
        meta = _d._oembed_title(vid)
        title, channel = meta["title"], meta["channel"]
    if vid and not channel:
        channel = _d._blocking.channel_of(db, vid)    # a row the card showed knows its author
    if not vid:
        rq = _d._results_query(raw)
        if rq:                                       # a RESULTS link is a search, already written
            return _d.apply_action("search", {**p, "query": rq})
    if not vid:                                     # not URL/id → search by name
        q = str(p.get("query") or p.get("q") or raw or "").strip()
        db["last_query"] = q
        # Real LOADER (bug 2026-07-23, "there is no loader showing that you are searching"): _search_id scrapes
        # the network (several seconds) — without this the card looked COMPLETELY empty in the meantime,
        # indistinguishable from "nothing requested". Save+emit NOW (before network) so widget.js paints the
        # spinner immediately; the final load turns it off.
        db["loading"], db["loading_query"] = True, q
        _d.store.save(_d.WID, db)
        r = _d._search_id(q, db.get("blocked_channels"), _d._blocked_ids(db))
        vid = r["videoId"]
        latest = r["latest"]
        if vid and not title:
            title = r["title"]
        channel, published = r["channel"], r["published"]
    db["loading"], db["loading_query"] = False, ""
    if not vid:
        _d.store.save(_d.WID, db)                          # turn off loader even if nothing was found
        return {"ok": False, "error": "no_video", "message": "No encontré ese vídeo."}
    db["player_error"] = ""   # fresh video, clean slate (V2-401)
    db["blocked_notice"] = {}
    db["pick_explicit"] = explicit
    db["videoId"] = vid
    db["url"] = "https://www.youtube.com/watch?v=" + vid
    db["title"] = title or db["url"]
    db["channel"] = channel                          # V2-057: VERIFIABLE metadata in the card
    db["published"] = published                      # e.g. "2 days ago" — confirms it is the correct one
    db["latest"] = latest                            # most recent requested (date order)
    # If the loaded video happens to BE in the list, `next` continues from there; otherwise the list is a
    # queue that will start after this video ends (pos=-1 → ended plays list[0]).
    db["pos"] = next((i for i, it in enumerate(db.get("list") or []) if it.get("videoId") == vid), -1)
    db["paused"] = False
    _d.library.record_play(db, {"videoId": vid, "title": db["title"], "channel": channel, "url": db["url"]})
    _d._sound.wants_sound(db)                           # V2-791: a video he asked to watch is heard
    _d.library.apply_prefs(db, fresh=not had_video)
    _d._goto(db, "player")                              # V2-755: he asked to watch it, so show it
    notice = _d._blocking.explicit_link_notice(db, explicit, channel, db["title"])
    return {**_d._bump(db, "load"), **notice}


def _a_add(action, p, db) -> dict:
    # V2-366 — into the LIST, never into the player: like YouTube's own "Add to queue", adding NEVER starts
    # playback (this is also what keeps `add` usable with the agent stopped — it is not a `produce` op).
    raw = str(p.get("url") or p.get("videoId") or "").strip()
    if isinstance(p.get("urls"), list):              # explicit list payload also accepted
        raw = " ".join(str(u) for u in p["urls"]) + " " + raw
    # SEVERAL links in one payload (V2-384 bis, measured 2026-08-27 14:38): the operator pastes two urls in
    # one sentence and the model emits ONE `add` with the pasted text — taking only the first id silently
    # dropped the rest. Every id in the text lands; the single-id path below stays byte-identical.
    vids = _d._YT_RE.findall(raw)
    if len(vids) > 1:
        added, positions = [], []
        lst = db.setdefault("list", [])
        for v in vids:
            if any(it.get("videoId") == v for it in lst):
                continue
            meta = _d._oembed_title(v)
            seq = max((int(it.get("added_seq") or 0) for it in lst), default=0) + 1
            lst.append({"videoId": v, "title": meta["title"] or ("youtu.be/" + v),
                        "channel": meta["channel"], "published": "",
                        "url": "https://www.youtube.com/watch?v=" + v,
                        "added_at": int(_d.time.time()), "added_seq": seq})
            added.append(lst[-1]["title"]); positions.append(len(lst))
        _d.store.save(_d.WID, db)
        return {"ok": True, "added": added, "positions": positions, "count": len(lst)}
    vid = _d._extract_id(raw)
    title = str(p.get("title") or "").strip()
    channel, published = "", ""
    if vid and not title:
        meta = _d._oembed_title(vid)                   # a pasted bare link still deserves a readable row
        title, channel = meta["title"], meta["channel"]
    pasted = bool(vid)                               # a link he handed over, not a search we resolved (V2-604)
    if vid and not channel:
        channel = _d._blocking.channel_of(db, vid)
    if not vid:                                     # not URL/id → search by name
        q = str(p.get("query") or p.get("q") or raw or "").strip()
        if not q:
            return {"ok": False, "error": "no_video", "message": "Dime qué vídeo añado (enlace o nombre)."}
        if (band := _rr.resolve(db.get("search_results") or [], q)) is not None:
            return _a_add_results(action, {"items": str(band + 1)}, db)   # a row he can SEE is not a new search
        db["adding"] = q                            # visible state while the network search runs
        _d.store.save(_d.WID, db)
        r = _d._search_id(q, db.get("blocked_channels"), _d._blocked_ids(db))
        db["adding"] = ""
        vid = r["videoId"]
        if vid and not title:
            title = r["title"]
        channel, published = r["channel"], r["published"]
    if not vid:
        _d.store.save(_d.WID, db)                          # turn the "adding" state off even on failure
        return {"ok": False, "error": "no_video", "message": "No encontré ese vídeo."}
    lst = db.setdefault("list", [])
    for i, it in enumerate(lst):                    # dedup by videoId: a repeated add is almost always a retry
        if it.get("videoId") == vid:
            notice = _d._blocking.explicit_link_notice(db, pasted, channel or it.get("channel") or "",
                                                       it.get("title") or title, queued=True)
            _d.store.save(_d.WID, db)
            return {"ok": True, "already_in_list": True, "position": i + 1,
                    "title": it.get("title"), "count": len(lst), **notice}
    url = "https://www.youtube.com/watch?v=" + vid
    # `added_seq` is the insertion order: several adds can land in the same SECOND, so `added_at` alone
    # cannot restore it (measured: sort_list by=added left a same-second batch in its current order).
    seq = max((int(it.get("added_seq") or 0) for it in lst), default=0) + 1
    lst.append({"videoId": vid, "title": title or ("youtu.be/" + vid), "channel": channel,
                "published": published, "url": url, "added_at": int(_d.time.time()), "added_seq": seq})
    if db.get("videoId") and db.get("pos", -1) < 0:
        # current video was loaded outside the list; keep it that way (ended → list[0] still correct)
        pass
    notice = _d._blocking.explicit_link_notice(db, pasted, channel, lst[-1]["title"], queued=True)
    _d.store.save(_d.WID, db)
    return {"ok": True, "position": len(lst), "title": lst[-1]["title"], "count": len(lst), **notice}


def _a_search(action, p, db) -> dict:
    # V2-402/V2-632 — a MEDIA search lands in the WIDGET, never in the results sheet; and since the
    # operator's redesign (2026-09-09) it lands on the DASHBOARD as its own numbered band, never in the
    # queue: results are something to CHOOSE FROM, the queue is what he chose. A new search REPLACES the
    # previous one (results are a view of the last question, not an archive). NOTHING starts playing
    # (V2-366's rule holds), and player state is untouched: a search must not interrupt playback.
    q = str(p.get("query") or p.get("q") or "").strip()
    q = _d._results_query(q) or q                       # a pasted results link is the query, decoded
    if not q:
        return {"ok": False, "error": "no_query", "message": "Dime qué vídeos busco."}
    # V2-756 — THE NUMBERS UNDER HIS FEET. Live session 74be8e9a (2026-09-23): «Ahora quiero que me
    # pongas el vídeo número tres» came back as `play_video(action=list)` — a SEARCH — three turns
    # running, and each one re-fetched the same query and rebuilt the band. He said it himself:
    # «Bueno, ponme el vídeo dos, que los has cambiado.» A search is the question «what is there?»,
    # and asking it twice cannot be allowed to change the answer he is already reading off the
    # screen. So the same question over the same band is ANSWERED, not re-run: nothing renumbers,
    # nothing is re-fetched, and the turn says out loud that it changed nothing (`unchanged`) so
    # the channel can tell a real search from one that did nothing at all.
    prev = db.get("search_results") or []
    # …but NOT when the band now holds something the operator has since refused: V2-634's rule is that
    # the refused never come back, and a video that failed to play (`player_error`) is blocklisted
    # between one search and the next. Re-asking then is not the same question.
    _stale = bool(prev) and (
        any(r.get("videoId") in _d._blocked_ids(db) for r in prev)
        or bool(_d._drop_blocked(list(prev), db.get("blocked_channels") or [])[1]))
    if prev and not _stale and _d._norm(q) == _d._norm(str(db.get("search_query") or "")):
        db["adding"] = ""
        _d._goto(db, "inicio")          # V2-757: nothing is re-run, but he still gets to SEE the answer
        _d.store.save(_d.WID, db)
        return {"ok": True, "unchanged": True, "count": len(prev), "query": q,
                "results": [r.get("title") for r in prev],
                "message": "Esos resultados ya están en pantalla, numerados."}
    try:
        n = int(p.get("n") or 6)
    except Exception:
        n = 6
    n = max(1, min(n, 10))
    db["adding"] = q                                # visible state while the network search runs (as `add`)
    _d.store.save(_d.WID, db)
    blocked = db.get("blocked_channels") or []
    bids = _d._blocked_ids(db)
    # Fetch a few extra when a filter exists, so blocking a channel does not shrink every search.
    hits = _d._search_many(q, n + (4 if blocked else 0) + (4 if bids else 0))
    hits, n_blocked = _d._drop_blocked(hits, blocked)
    hits = [h for h in hits if h["videoId"] not in bids][:n]   # V2-634: the refused never come back
    db["last_query"] = q
    db["adding"] = ""
    if not hits:
        _d.store.save(_d.WID, db)                          # turn the state off even when nothing was found
        if n_blocked:
            # Results existed and the operator's own filter removed them — saying «no videos» would read
            # as a worse search and invite retries against a wall he built himself (V2-414's confound).
            return {"ok": False, "error": "all_blocked", "blocked_out": n_blocked,
                    "message": "Había resultados pero todos eran de canales que tienes bloqueados."}
        return {"ok": False, "error": "no_video", "message": "No encontré vídeos de eso."}
    db["search_results"] = [{"videoId": h["videoId"],
                             "title": h["title"] or ("youtu.be/" + h["videoId"]),
                             "channel": h["channel"], "published": h["published"],
                             "url": "https://www.youtube.com/watch?v=" + h["videoId"],
                             "source": "youtube"} for h in hits]
    db["search_query"] = q
    db["searched_at"] = int(_d.time.time())
    # V2-757 — A BAND HE CANNOT SEE IS NOT AN ANSWER. Live session f84f91ef (2026-09-23): with
    # Ronaldinho playing, he asked for videos of the moon landing. The search ran, six numbered
    # results landed on the dashboard — and the card stayed on the PLAYER, so all he had in front of
    # him was the old video. «Ya, pero yo no veo el catálogo, solo veo el vídeo de Ronaldinho.»
    # Three turns of friction followed, and the engine spent them insisting the results were there.
    # This is the exact mirror of what V2-755 installed for playback («a video ARRIVING means
    # watching it»): a search ARRIVING means looking at what it found. The player is untouched —
    # whatever was sounding keeps sounding, which is V2-366's rule and has not changed.
    _d._goto(db, "inicio")
    _d.store.save(_d.WID, db)
    out = {"ok": True, "results": [r["title"] for r in db["search_results"]],
           "count": len(db["search_results"]), "query": q}
    if n_blocked:
        out["blocked_out"] = n_blocked               # the ack can say «and N more from blocked channels»
    return out


def _a_play_result(action, p, db) -> dict:
    # V2-632 — «reproduce el tercero» over the dashboard's search band. 1-based, like every spoken number.
    res = db.get("search_results") or []
    if not res:
        return {"ok": False, "error": "no_results", "message": "No hay resultados de búsqueda ahora mismo."}
    ref = p.get("item") if p.get("item") is not None else p.get("n")
    i = _rr.resolve(res, ref)          # a number, or the title/channel he named (2026-10-14, `result_refs`)
    if i is None:
        if str(ref or "").strip().isdigit():
            return {"ok": False, "error": "bad_index", "count": len(res),
                    "message": _d._langs.words("youtube.results.only_n", default="").format(n=len(res))}
        return {"ok": False, "error": "item_not_found", "item": ref, "count": len(res),
                "message": _d._langs.words("youtube.results.which", default="")}
    it = res[i]
    _d._swap_to(db, it)   # V2-634: the shared field-set (pick_explicit=False and queue position inside)
    _d._goto(db, "player")                              # V2-755: he asked to watch it, so show it
    r = _d._bump(db, "load")
    r["position"] = i + 1
    return r


def _a_add_results(action, p, db) -> dict:
    # V2-632 — «añade los tres primeros a la cola» / «añádelos todos». Payload: items="1,2,3" | [1,2,3] |
    # "all" (or a single n). The queue gets rows in the same shape `add` writes, so play_item/next/remove
    # keep working on them untouched.
    res = db.get("search_results") or []
    if not res:
        return {"ok": False, "error": "no_results", "message": "No hay resultados de búsqueda ahora mismo."}
    raw = p.get("items", p.get("item", p.get("n", "")))
    idxs = _rr.indices(res, raw)        # numbers, «all», or the rows he named (2026-10-14, `result_refs`)
    if not idxs:
        return {"ok": False, "error": "no_items", "count": len(res),
                "message": "Dime cuáles añado (números, o «todos»)."}
    lst = db.setdefault("list", [])
    added, positions = [], []
    for i in idxs:
        h = res[i - 1]
        if any(it.get("videoId") == h.get("videoId") for it in lst):
            continue
        seq = max((int(it.get("added_seq") or 0) for it in lst), default=0) + 1
        lst.append({"videoId": h.get("videoId"), "title": h.get("title") or "",
                    "channel": h.get("channel") or "", "published": h.get("published") or "",
                    "url": h.get("url") or "", "added_at": int(_d.time.time()), "added_seq": seq})
        added.append(h.get("title") or "")
        positions.append(len(lst))
    _d.store.save(_d.WID, db)
    return {"ok": True, "added": added, "positions": positions, "count": len(lst)}


def _a_show_tab(action, p, db) -> dict:
    # V2-742 — THE CARD HAD FIVE FACES AND THE VOICE COULD REACH NONE OF THEM: with no action meaning «back
    # to the catalog», the model picked the nearest one, `clear_search`, which DESTROYS that list.
    #
    # `selectTab` has been the card's one navigation surface since V2-632 and nothing outside
    # the card could call it. So this declares what already exists rather than building a
    # second way to navigate — the tab list is the widget's own, and an unknown one is refused
    # instead of guessed, because a silent no-op is how «it says it will and it doesn't» starts.
    tab = str((p or {}).get("tab") or "").strip().lower()
    if tab not in _d._TABS:
        # V2-754 — the model wrote `home` for «inicio» and this refused it: a correct order, a correct
        # action, thrown away over vocabulary (session 3afe34a8). The faces' aliases are declared in
        # the manifest next to the ids, so the model reads the same words the widget accepts.
        tab = _d._tab_alias(tab) or tab
    if tab not in _d._TABS:
        return {"ok": False, "error": "unknown_tab", "tab": tab, "tabs": list(_d._TABS)}
    # A SEQUENCE, not a flag: he can ask for the same face twice in a row («no, al inicio» after
    # the card already believes it is there), and a flag the card has consumed cannot fire again.
    _d._goto(db, tab)
    _d.store.save(_d.WID, db)
    from . import tab_answer as _ta               # 2026-10-11: the face's content IS the answer, not its name
    _res = _ta.result(db, tab)
    return {"ok": True, "tab": tab, **({"result": _res} if _res else {})}


def _a_clear_search(action, p, db) -> dict:
    db["search_results"], db["search_query"], db["searched_at"] = [], "", 0
    _d.store.save(_d.WID, db)
    return {"ok": True}


def _a_next(action, p, db) -> dict:
    from . import playability as _plays          # 2026-10-11: «nothing after it» is not «it can't play here»
    if (_refused := _plays.next_refusal(db)):
        return _refused
    lst = db.get("list") or []
    nxt = int(db.get("pos", -1)) + 1
    if not lst or nxt >= len(lst):
        return {"ok": False, "error": "end_of_list", "message": "No hay más vídeos en la lista."}
    return _d._play_pos(db, nxt, "next")
