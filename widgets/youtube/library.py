#
# youtube/library — the widget's OWN library: followed channels, watch history, preferences and saved lists.
#
# Operator's standing rule (2026-09-06): "our core, our engine, our memory, our widget are the ones who have
# control". None of this depends on a connector. The account connector, when its door can finally open
# (INI-032), only EXTENDS what lives here — it never becomes the source of truth, and nothing here degrades
# when it is absent, because nothing here ever asks it anything.
#
# It lives beside data.py rather than inside it for the reason the architecture ratchet exists: data.py was
# 843 LOC against the 900 ceiling for an unlisted file, so this arrives as a module instead of as the last
# straw on a god file.
#
import time

from .. import store

WID = "youtube"

# How much history is kept. Long enough to answer "what was that thing I watched last week", short enough
# that the store stays a store and not a log: the rows are ~120 bytes and view_data serves the whole db.
_HISTORY_MAX = 300

#: Preference keys this widget can actually ENFORCE, each with the mechanism that enforces it. A preference
#: we cannot honour is not stored as though we could — that is the "true sentence about the wrong mechanism"
#: failure V2-603 paid for. Anything outside this table lands in `prefs_notes` and SAYS so.
_ENFORCEABLE = {
    "min_definition": "el reproductor compara la calidad disponible del vídeo con este mínimo",
    "captions": "los subtítulos se activan solos al cargar cada vídeo",
    "volume": "el volumen de arranque de cada vídeo",
}

# YouTube's own quality level names → vertical resolution. `getAvailableQualityLevels` is the ONLY honest
# source of a video's definition we own: the results page does not publish it (measured 2026-09-07 — of ~20
# hits, only 4K carries a badge at all), so a "minimum 720p" rule can be checked when the player has the
# video and never before. `auto`/`default` carry no information and are ignored rather than guessed at.
_QUALITY = {
    "tiny": 144, "small": 240, "medium": 360, "large": 480,
    "hd720": 720, "hd1080": 1080, "hd1440": 1440, "hd2160": 2160, "highres": 2160,
}


def seed_fields() -> dict:
    """The library's slice of the widget seed, merged into `data._SEED` so there is ONE seed, not two."""
    return {
        # Channels the operator follows — OUR subscription list, built by voice and owned by us. The mirror
        # image of `blocked_channels`: that one says what he refuses, this one says what he wants.
        "channels": [],           # [{name, added_at}]
        # What was actually PLAYED, recorded by the player itself. This is the piece the YouTube API can
        # never give us (watchHistory has returned empty for every account since 2016, INI-032 §6): we own
        # it precisely BECAUSE we are the ones playing the video.
        "history": [],            # [{videoId, title, channel, url, played_at, quality}]
        # Enforceable preferences (see _ENFORCEABLE) — the filters the operator sets by voice.
        "prefs": {},
        # Everything he asked for that we cannot enforce, kept verbatim so the brain can honour it by
        # judgement and the card can show it as what it is: a note, not a rule.
        "prefs_notes": [],        # [{text, added_at}]
        # Saved queues, so `list` stops being the only one that ever existed.
        "lists": [],              # [{name, items, saved_at}]
        # Definition the player REPORTED for the current video (0 = it has not said). Its own
        # field rather than a derived one: it is a fact from outside, like `player_error`.
        "quality": 0,
    }


def _norm(s: str) -> str:
    from . import data
    return data._norm(s)


def quality_rank(level: str) -> int:
    """Vertical resolution of a YouTube quality level name, or 0 when the name carries no information."""
    return int(_QUALITY.get(str(level or "").strip().lower(), 0))


def best_quality(levels) -> int:
    """The highest resolution the player says this video HAS. 0 = it told us nothing (never a verdict)."""
    return max((quality_rank(l) for l in (levels or [])), default=0)


def min_definition(db: dict) -> int:
    try:
        return int((db.get("prefs") or {}).get("min_definition") or 0)
    except (TypeError, ValueError):
        return 0


def record_play(db: dict, item: dict) -> None:
    """Called by data.py the moment a video actually starts. Deduped by moving an existing row to the front
    rather than appending a second one: "what have I been watching" wants distinct videos, and a replayed
    video is the SAME video watched again — its `played_at` moves, its row does not multiply."""
    vid = str((item or {}).get("videoId") or "").strip()
    if not vid:
        return
    hist = db.setdefault("history", [])
    row = next((h for h in hist if h.get("videoId") == vid), None)
    if row is not None:
        hist.remove(row)
        row["played_at"] = int(time.time())
        row["plays"] = int(row.get("plays") or 1) + 1
    else:
        row = {"videoId": vid, "title": str(item.get("title") or "")[:200],
               "channel": str(item.get("channel") or "")[:120],
               "url": item.get("url") or ("https://www.youtube.com/watch?v=" + vid),
               "played_at": int(time.time()), "plays": 1, "quality": 0}
    hist.insert(0, row)
    del hist[_HISTORY_MAX:]


def _find_channel(db: dict, name: str) -> "dict | None":
    n = _norm(name)
    if not n:
        return None
    chans = db.get("channels") or []
    for c in chans:                                     # exact first, so «Ana» never removes «Ana María»
        if _norm(c.get("name")) == n:
            return c
    return next((c for c in chans if n in _norm(c.get("name"))), None)


def _find_list(db: dict, name: str) -> "dict | None":
    n = _norm(name)
    if not n:
        return None
    lists = db.get("lists") or []
    for L in lists:
        if _norm(L.get("name")) == n:
            return L
    return next((L for L in lists if n in _norm(L.get("name"))), None)


def _row(h: dict) -> dict:
    """A history/library row shaped exactly like a `list` row, so everything the player already knows how to
    do with a queue item — play_item, remove, move, next — works on these without a second code path."""
    return {"videoId": h.get("videoId"), "title": h.get("title") or ("youtu.be/" + str(h.get("videoId"))),
            "channel": h.get("channel") or "", "published": h.get("published") or "",
            "url": h.get("url") or ("https://www.youtube.com/watch?v=" + str(h.get("videoId"))),
            "added_at": int(time.time()), "added_seq": 0}


def _fill_list(db: dict, rows: list) -> int:
    """Replace the queue with `rows`. Used by the actions that ANSWER with videos (history, a channel, a
    saved list): the list is this widget's one place where a set of videos is chosen from, and sending
    results anywhere else would be the results-sheet mistake V2-402 already corrected."""
    lst = []
    for i, r in enumerate(rows):
        row = _row(r)
        row["added_seq"] = i + 1
        lst.append(row)
    db["list"] = lst
    db["pos"] = -1
    return len(lst)


# Spoken names for the enforceable keys. The operator says "calidad mínima", not "min_definition", and the
# model relays his words: a key table that only knows its own identifiers turns every real sentence into an
# unknown preference. One-way (spoken → key), so the answer always names the key back.
_KEY_ALIASES = {
    "min_definition": "min_definition", "definition": "min_definition", "quality": "min_definition",
    "calidad": "min_definition", "calidad minima": "min_definition", "resolucion": "min_definition",
    "resolucion minima": "min_definition", "min_quality": "min_definition",
    "captions": "captions", "subtitles": "captions", "subtitulos": "captions",
    "volume": "volume", "volumen": "volume",
}

_TRUE = {"1", "true", "on", "si", "yes", "activar", "activalos", "activados", "activado",
         "ponlos", "siempre", "encender", "encendidos"}
_FALSE = {"0", "false", "off", "no", "quitar", "quitalos", "desactivar", "desactivalos",
          "desactivados", "desactivado", "nunca", "apagar", "apagados"}


def _pref_value(key: str, raw) -> "tuple[object, str]":
    """(value, error). Parses the operator's words into the type the key enforces — «720p», «sí», «al 40».

    The value goes through the SAME `_norm` as the key, accents included. It did not at first, and the very
    first sentence an operator says in Spanish — «pon los subtítulos, sí» — was refused because the table
    held `si` and he said `sí`: a value vocabulary matched more strictly than the key vocabulary rejects
    exactly the words the widget was written to understand."""
    s = _norm(raw if raw is not None else "")
    if key == "min_definition":
        digits = "".join(ch for ch in s if ch.isdigit())
        if not digits:
            return None, "Dime la calidad mínima en píxeles, por ejemplo 720."
        n = int(digits[:5])
        if n not in (144, 240, 360, 480, 720, 1080, 1440, 2160):
            # Not a rejection of his taste — a rejection of a number the player can never report, which
            # would make the rule silently unenforceable (the failure this whole module is built against).
            return None, ("Las calidades que el reproductor sabe medir son 144, 240, 360, 480, 720, 1080, "
                          "1440 y 2160.")
        return n, ""
    if key == "captions":
        if s in _TRUE:
            return True, ""
        if s in _FALSE:
            return False, ""
        return None, "Dime si quiero los subtítulos activados o desactivados."
    if key == "volume":
        digits = "".join(ch for ch in s if ch.isdigit())
        if not digits:
            return None, "Dime un volumen de 0 a 100."
        return max(0, min(100, int(digits[:3]))), ""
    return None, "No sé aplicar esa preferencia."


def apply(action: str, p: dict, db: dict) -> "dict | None":
    """The library's actions. Returns None when `action` is not one of ours, so data.py keeps owning its own
    dispatch and the two cannot disagree about who answers what."""

    if action == "follow_channel":
        ch = str(p.get("channel") or p.get("name") or p.get("item") or "").strip()[:120]
        if not ch:
            return {"ok": False, "error": "no_channel", "message": "Dime qué canal sigo."}
        if _find_channel(db, ch) is not None:
            return {"ok": True, "already": True, "channel": ch,
                    "channels": [c.get("name") for c in db.get("channels") or []]}
        # Following a channel he has blocked is a contradiction, and leaving both standing would make his
        # own searches drop the channel he just said he wants. The newer sentence wins, and the answer says
        # the older one was undone — a filter that disappears in silence is a filter he cannot trust.
        blocked = db.setdefault("blocked_channels", [])
        n = _norm(ch)
        unblocked = [b for b in blocked if _norm(b) == n or n in _norm(b) or _norm(b) in n]
        for b in unblocked:
            blocked.remove(b)
        db.setdefault("channels", []).append({"name": ch, "added_at": int(time.time())})
        store.save(WID, db)
        out = {"ok": True, "channel": ch, "channels": [c.get("name") for c in db["channels"]]}
        if unblocked:
            out["unblocked"] = unblocked
        return out

    if action == "unfollow_channel":
        ch = str(p.get("channel") or p.get("name") or p.get("item") or "").strip()
        hit = _find_channel(db, ch)
        if hit is None:
            return {"ok": False, "error": "not_followed", "channel": ch,
                    "channels": [c.get("name") for c in db.get("channels") or []],
                    "message": "No sigo ese canal."}
        db["channels"].remove(hit)
        store.save(WID, db)
        return {"ok": True, "channel": hit.get("name"),
                "channels": [c.get("name") for c in db["channels"]]}

    if action == "channel_videos":
        # The latest from a channel, WITHOUT an account: search by the channel's name sorted by date and keep
        # only the hits whose channel really matches. Honest about what it is — a search, not a subscription
        # feed — so it works today for every operator, connected or not.
        from . import data
        ch = str(p.get("channel") or p.get("name") or p.get("item") or "").strip()
        if not ch:
            names = [c.get("name") for c in db.get("channels") or []]
            if len(names) != 1:
                return {"ok": False, "error": "no_channel", "channels": names,
                        "message": "Dime de qué canal." if names else "Todavía no sigues ningún canal."}
            ch = names[0]
        known = _find_channel(db, ch)
        if known is not None:
            ch = known.get("name") or ch
        try:
            n = max(1, min(int(p.get("n") or 6), 10))
        except (TypeError, ValueError):
            n = 6
        db["adding"] = ch                                # visible state while the network search runs
        store.save(WID, db)
        hits = data._search_many(ch + " últimos vídeos", n + 8)
        db["adding"] = ""
        want = _norm(ch)
        mine = [h for h in hits if want and (want in _norm(h.get("channel")) or _norm(h.get("channel")) in want)]
        mine, n_blocked = data._drop_blocked(mine, db.get("blocked_channels"))
        if not mine:
            store.save(WID, db)
            return {"ok": False, "error": "no_video", "channel": ch,
                    "message": "No encontré vídeos recientes de ese canal."}
        count = _fill_list(db, mine[:n])
        store.save(WID, db)
        out = {"ok": True, "channel": ch, "count": count, "titles": [r["title"] for r in db["list"]]}
        if n_blocked:
            out["blocked_out"] = n_blocked
        return out

    if action == "show_history":
        hist = db.get("history") or []
        if not hist:
            return {"ok": False, "error": "no_history",
                    "message": "Todavía no he reproducido ningún vídeo, así que no hay historial."}
        q = str(p.get("query") or p.get("q") or "").strip()
        rows = hist
        if q:                                            # «el que vi de cocina» — search HIS history, not the net
            nq = _norm(q)
            rows = [h for h in hist if nq in _norm(" ".join([h.get("title") or "", h.get("channel") or ""]))]
            if not rows:
                return {"ok": False, "error": "no_match", "query": q,
                        "message": "No encuentro nada así en el historial."}
        try:
            n = max(1, min(int(p.get("n") or 10), 25))
        except (TypeError, ValueError):
            n = 10
        count = _fill_list(db, rows[:n])
        db["list_name"] = ("Historial: " + q) if q else "Historial"
        store.save(WID, db)
        return {"ok": True, "count": count, "total": len(hist), "query": q,
                "titles": [r["title"] for r in db["list"]]}

    if action == "clear_history":
        n = len(db.get("history") or [])
        db["history"] = []
        store.save(WID, db)
        return {"ok": True, "cleared": n}

    if action == "set_preference":
        raw_key = str(p.get("key") or p.get("name") or p.get("preference") or "").strip()
        key = _KEY_ALIASES.get(_norm(raw_key), "")
        value = p.get("value") if p.get("value") is not None else p.get("level")
        if not key:
            # Not enforceable — and that is said out loud rather than stored as if it were a rule. The brain
            # still receives it (view_data publishes prefs_notes), so it can honour it by judgement.
            text = " ".join(x for x in [raw_key, "" if value is None else str(value)] if x).strip()[:200]
            if not text:
                return {"ok": False, "error": "no_preference",
                        "message": "Dime qué preferencia guardo.", "enforceable": sorted(_ENFORCEABLE)}
            notes = db.setdefault("prefs_notes", [])
            if not any(_norm(x.get("text")) == _norm(text) for x in notes):
                notes.append({"text": text, "added_at": int(time.time())})
                del notes[:max(0, len(notes) - 20)]
            store.save(WID, db)
            return {"ok": True, "stored_as": "note", "note": text, "enforceable": sorted(_ENFORCEABLE),
                    "message": ("Lo guardo y lo tendré en cuenta, pero no puedo forzarlo automáticamente: "
                                "lo que sí aplico solo es " + ", ".join(sorted(_ENFORCEABLE)) + ".")}
        val, err = _pref_value(key, value)
        if err:
            return {"ok": False, "error": "bad_value", "key": key, "message": err}
        db.setdefault("prefs", {})[key] = val
        store.save(WID, db)
        return {"ok": True, "stored_as": "rule", "key": key, "value": val,
                "how": _ENFORCEABLE[key], "prefs": dict(db["prefs"])}

    if action == "clear_preference":
        raw_key = str(p.get("key") or p.get("name") or p.get("preference") or "").strip()
        key = _KEY_ALIASES.get(_norm(raw_key), "")
        prefs = db.setdefault("prefs", {})
        if key and key in prefs:
            prefs.pop(key)
            store.save(WID, db)
            return {"ok": True, "key": key, "prefs": dict(prefs)}
        notes = db.setdefault("prefs_notes", [])
        n = _norm(raw_key)
        hit = next((x for x in notes if n and n in _norm(x.get("text"))), None)
        if hit is not None:
            notes.remove(hit)
            store.save(WID, db)
            return {"ok": True, "note": hit.get("text"), "prefs": dict(prefs)}
        return {"ok": False, "error": "not_set", "key": raw_key, "prefs": dict(prefs),
                "message": "No tengo esa preferencia guardada."}

    if action == "save_list":
        lst = db.get("list") or []
        if not lst:
            return {"ok": False, "error": "empty_list",
                    "message": "La lista está vacía, no hay nada que guardar."}
        name = str(p.get("name") or p.get("title") or p.get("item") or db.get("list_name") or "").strip()[:80]
        if not name:
            return {"ok": False, "error": "no_name", "message": "Dime con qué nombre la guardo."}
        lists = db.setdefault("lists", [])
        prev = _find_list(db, name)
        if prev is not None:
            lists.remove(prev)
        lists.append({"name": name, "items": [dict(it) for it in lst], "saved_at": int(time.time())})
        db["list_name"] = name
        store.save(WID, db)
        return {"ok": True, "name": name, "count": len(lst), "replaced": prev is not None,
                "lists": [L.get("name") for L in lists]}

    if action == "open_list":
        name = str(p.get("name") or p.get("title") or p.get("item") or "").strip()
        names = [L.get("name") for L in db.get("lists") or []]
        hit = _find_list(db, name)
        if hit is None:
            return {"ok": False, "error": "no_list", "name": name, "lists": names,
                    "message": ("No tengo ninguna lista guardada con ese nombre." if names
                                else "Todavía no has guardado ninguna lista.")}
        # Opening REPLACES the queue and does not start playback — the same rule `add` and `search` follow
        # (V2-366: only an explicit play starts a video). What is playing keeps playing.
        count = _fill_list(db, hit.get("items") or [])
        db["list_name"] = hit.get("name") or name
        store.save(WID, db)
        return {"ok": True, "name": db["list_name"], "count": count,
                "titles": [r["title"] for r in db["list"]]}

    if action == "delete_list":
        name = str(p.get("name") or p.get("title") or p.get("item") or "").strip()
        hit = _find_list(db, name)
        if hit is None:
            return {"ok": False, "error": "no_list", "name": name,
                    "lists": [L.get("name") for L in db.get("lists") or []],
                    "message": "No tengo ninguna lista guardada con ese nombre."}
        db["lists"].remove(hit)
        store.save(WID, db)
        return {"ok": True, "name": hit.get("name"), "lists": [L.get("name") for L in db["lists"]]}

    if action == "player_quality":
        # Internal, fired by widget.js from the IFrame API's own report. This is the ONLY moment a video's
        # definition is knowable (the results page does not publish it), so it is where a "minimum 720p"
        # rule is checked. It WARNS and never skips: the operator asked for THIS video, and an explicit
        # order outranks a standing filter — the same line block_channel already draws for a pasted link.
        vid = str(p.get("videoId") or db.get("videoId") or "").strip()
        best = best_quality(p.get("levels"))
        if not vid or not best:
            return {"ok": True, "known": False}          # told us nothing: never a verdict, never a warning
        for h in db.get("history") or []:
            if h.get("videoId") == vid:
                h["quality"] = best
                break
        db["quality"] = best
        store.save(WID, db)
        want = min_definition(db)
        out = {"ok": True, "known": True, "quality": best, "min": want, "videoId": vid}
        if want and best < want:
            out["below_min"] = True
            out["message"] = ("Este vídeo solo llega a %dp y tienes puesto un mínimo de %dp." % (best, want))
        return out

    return None


def apply_prefs(db: dict, fresh: bool) -> None:
    """Put the operator's standing preferences on the video that is about to start.

    `captions` is re-asserted on EVERY video, which is what a preference about content means and what the
    player already does with the flag (V2-590). `volume` is only applied when playback is starting from
    nothing (`fresh`): re-imposing it on every item would fight the operator — he turns it down for one
    video and the next one shouts again — and a preference that undoes his last explicit order is not a
    preference, it is a bug with a settings screen."""
    prefs = db.get("prefs") or {}
    if "captions" in prefs:
        db["captions"] = bool(prefs["captions"])
    if fresh and "volume" in prefs:
        try:
            db["volume"] = max(0, min(100, int(prefs["volume"])))
            db["muted"] = db["volume"] == 0
        except (TypeError, ValueError):
            pass
