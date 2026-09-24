"""The TORRENTS section of Archivos — catalogue, downloads, seeds (V2-764).

The operator merged the separate download widget into the file manager: *«uno será la biblioteca del sistema de
archivos y la otra sección será la de torrents… tres subapartados: el dashboard, por si pido catálogos de cosas
que se puedan descargar… descargas y semillas»*. A torrent is a file on its way to the library, so it lives in
the widget that owns the library.

Three sub-tabs, one object each:
  · **catalogo** — what the network OFFERS for a query (`service.catalog`): nothing is downloaded until he picks.
    The old widget's `search` went straight to downloading the first magnet; a catalogue is the thing he asked
    for («catálogos de cosas que se puedan descargar»).
  · **descargas** — what is downloading now.
  · **semillas** — what finished and is still shared back.

The row/title logic is the retired `widgets/torrent/data.py`'s, moved here unchanged in meaning: live status is
read from `connectors.torrent.service.active()` on every render — the client is a SYSTEM tool, so a download
started by the video player or by a worker shows up on the same shelf — and `titles` only remembers what he
asked for until the metadata names the torrent itself. Playing a row hands it to the surface that plays it
through `nucleo/torrent_router` (the isolation rule: a widget never reaches into a sibling's store).

State lives in Archivos' own store under `db["torrents"]` and `db["section"]`; this module never saves — the
caller does, once, like every other action of the widget.
"""
from __future__ import annotations

import re
import time

SECTIONS = ("biblioteca", "torrents")
TABS = ("catalogo", "descargas", "semillas")


def seed() -> dict:
    return {"tab": "catalogo", "catalog": {"query": "", "releases": [], "at": 0, "error": ""},
            "titles": {}, "error": ""}


def state(db: dict) -> dict:
    t = db.get("torrents")
    if not isinstance(t, dict):
        t = seed()
        db["torrents"] = t
    for k, v in seed().items():
        t.setdefault(k, v)
    return t


def _svc():
    """Deferred so the catalogue of widgets never imports libtorrent just to list Archivos."""
    from connectors.torrent import service
    return service


def available() -> bool:
    try:
        return bool(_svc().available())
    except Exception:  # noqa: BLE001
        return False


def unavailable_reason() -> str:
    try:
        return _svc().unavailable_reason()
    except Exception:  # noqa: BLE001
        return "el cliente de descargas no está disponible en esta instalación"


def _row(st: dict, titles: dict) -> dict:
    rid = st.get("id") or ""
    pct = int(round(float(st.get("progress") or 0) * 100))
    kind = st.get("kind") or ""
    playable = bool(st.get("playable"))
    complete = pct >= 100 or st.get("state") == "seeding"
    return {
        "id": rid,
        "title": st.get("name") or titles.get(rid) or "Buscando fuentes…",
        "kind": kind or "other",
        "file_name": st.get("file_name") or "",
        "playable": playable,
        "group": st.get("group") or ("seed" if st.get("state") == "seeding" else "download"),
        "state": st.get("state") or "",
        "progress": pct,
        "complete": complete,
        "download_rate": int(st.get("download_rate") or 0),
        "num_peers": int(st.get("num_peers") or 0),
        "downloaded": int(st.get("downloaded") or 0),
        "size": int(st.get("size") or 0),
        "streamable": bool(st.get("streamable")),
        "can_play": (kind == "video" and playable) or (kind == "audio" and playable and complete),
    }


def live_rows(db: dict) -> list[dict]:
    if not available():
        return []
    titles = state(db).get("titles") or {}
    out = []
    try:
        for st in _svc().active():
            if st.get("ok"):
                out.append(_row(st, titles))
    except Exception:  # noqa: BLE001 — a viewer never crashes on a status read
        return []
    return out


def _public_release(i: int, r: dict) -> dict:
    """A catalogue row as the CARD sees it: numbered from 1 (what he says: «la tercera»), no magnet — the card
    downloads by number, so the link never has to travel to the browser."""
    return {"n": i + 1, "title": r.get("title") or "", "size": r.get("size") or "",
            "seeders": int(r.get("seeders") or 0), "leechers": int(r.get("leechers") or 0),
            "resolution": r.get("resolution") or "", "kind": r.get("kind") or "",
            "published": r.get("published") or ""}


def view(db: dict) -> dict:
    t = state(db)
    avail = available()
    rows = live_rows(db) if avail else []
    cat = t.get("catalog") or {}
    return {
        "tab": t.get("tab") if t.get("tab") in TABS else "catalogo",
        "available": avail,
        "unavailable_reason": "" if avail else unavailable_reason(),
        "error": t.get("error") or "",
        "catalog": {"query": cat.get("query") or "", "error": cat.get("error") or "",
                    "releases": [_public_release(i, r) for i, r in enumerate(cat.get("releases") or [])]},
        "downloads": [r for r in rows if r["group"] != "seed"],
        "seeds": [r for r in rows if r["group"] == "seed"],
    }


def refs(db: dict) -> list[dict]:
    """Two classes of row, two fields (the V2-026 rule): a catalogue entry is picked by `item`, a live
    download by `id` — «la segunda» of the catalogue must never cancel the second download."""
    out = []
    for i, r in enumerate((state(db).get("catalog") or {}).get("releases") or []):
        out.append({"id": str(i + 1), "label": str(r.get("title") or ""), "field": "item", "hint": "catálogo"})
    for r in live_rows(db):
        out.append({"id": r["id"], "label": r["title"], "field": "id",
                    "hint": "semilla" if r["group"] == "seed" else "descarga"})
    return out


def digest(db: dict) -> str:
    t = state(db)
    tab = t.get("tab") if t.get("tab") in TABS else "catalogo"
    head = f"ARCHIVOS › TORRENTS › {tab.upper()}"
    if tab == "catalogo":
        cat = t.get("catalog") or {}
        rels = cat.get("releases") or []
        if cat.get("error"):
            return f"{head}: {cat['error']}"
        if not rels:
            return f"{head}: vacío — todavía no se ha buscado nada."
        rows = [f"{i + 1}. {r.get('title', '')[:70]} ({r.get('size') or '?'}, {r.get('seeders', 0)} semillas)"
                for i, r in enumerate(rels[:8])]
        more = f" (y {len(rels) - 8} más)" if len(rels) > 8 else ""
        return f"{head} de «{cat.get('query', '')}»: " + " | ".join(rows) + more
    if not available():
        return f"{head}: {unavailable_reason()}."
    rows = live_rows(db)
    shown = [r for r in rows if (r["group"] == "seed") == (tab == "semillas")]
    if not shown:
        return f"{head}: vacío."
    return f"{head}: " + " | ".join(f"«{r['title'][:60]}» {r['progress']}%" for r in shown[:6])


# ── resolving what he said ──────────────────────────────────────────────────────────────────────────────────
def _spec(action: str, key: str) -> str:
    try:
        from widgets import runtime as _rt
        return str(((((_rt.get("archivos") or {}).get("actions") or {}).get(action) or {}).get("payload")
                    or {}).get(key) or "")
    except Exception:  # noqa: BLE001
        return ""


def resolve_section(given: str) -> str:
    from widgets import enums as _enums
    return _enums.resolve(_spec("show_section", "section"), str(given or ""))


def resolve_tab(given: str) -> str:
    from widgets import enums as _enums
    return _enums.resolve(_spec("show_section", "tab"), str(given or ""))


_ORDINALS = {"primer": 1, "primera": 1, "primero": 1, "segund": 2, "tercer": 3, "cuart": 4, "quint": 5,
             "sext": 6, "septim": 7, "séptim": 7, "octav": 8, "noven": 9, "decim": 10, "décim": 10,
             "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5}
_WORD_NUM = {"uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7,
             "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12, "one": 1, "two": 2, "three": 3,
             "four": 4, "five": 5}


def pick(releases: list, item) -> int:
    """The catalogue index he meant — by number, by ordinal («la tercera»), or by words of the title — or -1.
    Never the nearest guess: an ambiguous title match is -1, and the reply asks."""
    if not releases:
        return -1
    s = str(item if item is not None else "").strip().lower()
    if not s:
        return -1
    m = re.fullmatch(r"\D{0,12}?(\d{1,2})\D{0,12}", s)      # «3», «la 3», «número 3» — not «1080p»
    if m:
        n = int(m.group(1))
        if 1 <= n <= len(releases):
            return n - 1
    for tok in re.findall(r"\w+", s):
        for k, n in _ORDINALS.items():
            if tok.startswith(k):
                return n - 1 if n <= len(releases) else -1
        if tok in _WORD_NUM:
            n = _WORD_NUM[tok]
            return n - 1 if n <= len(releases) else -1
    words = [w for w in re.findall(r"\w+", s) if len(w) > 2]
    if not words:
        return -1
    hits = [i for i, r in enumerate(releases)
            if all(w in str(r.get("title") or "").lower() for w in words)]
    return hits[0] if len(hits) == 1 else -1


def _remember_title(t: dict, rid: str, title: str, active_ids: set) -> None:
    if not (rid and title):
        return
    titles = t.setdefault("titles", {})
    titles[rid] = title
    for k in list(titles.keys()):              # bounded: a title for a gone download is dead weight
        if k not in active_ids and k != rid:
            titles.pop(k, None)


def _keep(payload: dict) -> bool:
    """Keep the file whatever its format — this section's whole job. Absent OR null means default (a model
    that sends `"keep": null` must not get the refusing behaviour, the retired widget's lesson)."""
    v = payload.get("keep")
    return True if v is None else bool(v)


# ── actions ─────────────────────────────────────────────────────────────────────────────────────────────────
def handle(db: dict, act: str, payload: dict) -> dict | None:
    """Result for a torrent/section action, or None when `act` is not one of them. Mutates `db`; the caller
    saves."""
    t = state(db)

    if act == "show_section":
        sec = resolve_section(payload.get("section") or "") if payload.get("section") else ""
        tab = resolve_tab(payload.get("tab") or "") if payload.get("tab") else ""
        if tab and not sec:
            sec = "torrents"                   # a sub-tab only exists inside Torrents
        if not sec:
            return {"ok": False, "error": "unknown_section",
                    "hint": "section: biblioteca | torrents; tab (solo en torrents): catalogo | descargas | semillas"}
        db["section"] = sec
        if sec == "torrents" and tab:
            t["tab"] = tab
        return {"ok": True, "section": sec, "tab": t.get("tab") if sec == "torrents" else ""}

    if act == "torrent_search":
        query = " ".join(str(payload.get("query") or "").split())[:200]
        if not query:
            return {"ok": False, "error": "dime qué busco: el título de la peli, la serie o lo que sea"}
        res = _svc().catalog(query)
        db["section"], t["tab"] = "torrents", "catalogo"
        if not res.get("ok"):
            t["catalog"] = {"query": query, "releases": [], "at": int(time.time()),
                            "error": res.get("error") or "no encontré nada para eso"}
            return {"ok": False, "error": t["catalog"]["error"], "section": "torrents", "tab": "catalogo"}
        rels = res.get("releases") or []
        t["catalog"] = {"query": query, "releases": rels, "at": int(time.time()), "error": ""}
        # What the turn can SAY — the rows, not «hecho» (V2-541: an action returns what it found).
        return {"ok": True, "section": "torrents", "tab": "catalogo", "count": len(rels),
                "matches": [_public_release(i, r) for i, r in enumerate(rels[:5])]}

    if act == "torrent_download":
        magnet = str(payload.get("magnet") or "").strip()
        title = ""
        if not magnet:
            rels = (t.get("catalog") or {}).get("releases") or []
            idx = pick(rels, payload.get("item"))
            if idx < 0:
                if not rels:
                    return {"ok": False, "error": "no hay catálogo: busca primero qué descargar (torrent_search)"}
                return {"ok": False, "error": "¿cuál? dime el número del catálogo (del 1 al "
                                              f"{len(rels)}) o parte del título"}
            magnet, title = rels[idx].get("magnet") or "", rels[idx].get("title") or ""
        res = _svc().add_magnet(magnet, keep=_keep(payload))
        if not res.get("ok"):
            t["error"] = res.get("error") or "no pude iniciar la descarga"
            return {"ok": False, "error": t["error"]}
        active = {r["id"] for r in live_rows(db)}
        _remember_title(t, res.get("id") or "", title, active)
        t["error"] = ""
        db["section"], t["tab"] = "torrents", "descargas"
        return {"ok": True, "id": res.get("id"), "title": title, "section": "torrents", "tab": "descargas"}

    if act == "torrent_open":
        rid = str(payload.get("id") or "").strip()
        if not rid:
            return {"ok": False, "error": "falta la descarga a reproducir"}
        try:
            st = _svc().status(rid)
        except Exception as e:  # noqa: BLE001
            st = {"ok": False, "error": str(e)[:160]}
        if not st.get("ok"):
            return {"ok": False, "error": st.get("error") or "esa descarga ya no está activa"}
        row = _row(st, t.get("titles") or {})
        from library import formats
        from nucleo import torrent_router
        if row["kind"] == "video":
            if not row["playable"]:
                return {"ok": False, "error": formats.refusal(row["file_name"])}
            if not (row["streamable"] or row["complete"]):
                return {"ok": False, "error": "aún no hay suficiente descargado para empezar a verla"}
            return torrent_router.route_video(rid, row["title"])
        if row["kind"] == "audio":
            if not row["playable"]:
                return {"ok": False, "error": formats.refusal(row["file_name"])}
            if not row["complete"]:
                return {"ok": False, "error": "espera a que termine de descargarse para reproducirla"}
            return torrent_router.route_audio(rid, row["title"])
        return {"ok": False, "error": "este fichero no se reproduce aquí — usa «Guardar» para pasarlo a la biblioteca"}

    if act == "torrent_save":
        rid = str(payload.get("id") or "").strip()
        if not rid:
            return {"ok": False, "error": "falta la descarga a guardar"}
        res = _svc().file_it(rid)
        if res.get("ok"):
            (t.get("titles") or {}).pop(rid, None)
        return res

    if act == "torrent_remove":
        rid = str(payload.get("id") or "").strip()
        if not rid:
            return {"ok": False, "error": "falta la descarga a cancelar"}
        res = _svc().remove(rid)
        (t.get("titles") or {}).pop(rid, None)
        return res

    if act == "torrent_poll":
        return {"ok": True, **view(db)}

    return None
