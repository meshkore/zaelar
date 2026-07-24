#
# musica — CARA del conector de música (V2-041) + LISTAS estilo Spotify (V2-058, Fase 1). Widget de SISTEMA
# hand-built (no generado): SÍ importa el core (connectors.music / connectors.spotify / config.credentials) porque
# corre en el proceso del server — igual que el owner de `mensajeria`.
#
# DOS responsabilidades:
#  · Conexión de Spotify (flujo guiado como los QR de mensajería) + control de reproducción (botones de la tarjeta).
#  · LISTAS/recientes/más-escuchadas persistidas en el estado del widget (widgets/_data/musica/state.json).
#
# REPRODUCCIÓN = el conector existente (connectors.music.control()); NUNCA se reinventa aquí. La reproducción por
# VOZ va por la tool play_music del FlashBrain; play_playlist/play desde el widget también convergen en ese seam.
#
# Invariante de persistencia: el bloque `yt` (audio oculto de YouTube) y las listas conviven en el MISMO store.
# view_data compone {db persistido} + {estado vivo (connected/mode/now_playing)} → guardar el compuesto preserva
# TODO (yt + playlists + counts). El proveedor youtube_audio hace read-modify-write del `yt`, así que respetamos
# el mismo contrato: nunca pisamos claves persistidas.
#
import re
import time
import unicodedata

from .. import store

WID = "musica"

_SEED = {"connected": False, "provider": "spotify", "can_connect": False, "own_client_id_set": False,
         "default_available": False, "redirect_uri": "", "now_playing": None}

_RECENT_CAP = 30
_TOP_CAP = 8


# ── helpers de normalización ────────────────────────────────────────────────────────────────────────────────
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return s.lower().strip()


def _slug(s: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", _norm(s)).strip("-")
    return base or "lista"


# ── store: db persistido (yt + playlists + recent + counts + view) ──────────────────────────────────────────
def _load_db() -> dict:
    try:
        db = store.load(WID, {}) or {}
    except Exception:
        db = {}
    if not isinstance(db, dict):
        db = {}
    db.setdefault("yt", {})
    db.setdefault("playlists", [])
    db.setdefault("recent", [])
    db.setdefault("counts", {})
    db.setdefault("view", {"kind": "home", "id": ""})
    return db


def _spotify_status() -> dict:
    try:
        from connectors.spotify import auth
        return auth.status()
    except Exception:
        return {}


def _now_playing() -> "dict | None":
    """Lo que suena AHORA (solo si hay cuenta Spotify conectada). Fail-open: nunca rompe la tarjeta."""
    try:
        from connectors import music
        np = music.now_playing()
        if not np:
            return None
        t = np.track
        return {"playing": bool(np.playing), "device": np.device or "", "volume": np.volume,
                "title": (t.title if t else ""), "artist": (t.artist if t else ""),
                "album": (t.album if t else ""), "art": (t.art if t else "")}
    except Exception:
        return None


def _live_fields(db: dict) -> dict:
    """Estado VIVO (recomputado cada lectura): conexión de Spotify + qué modo pinta la tarjeta + now_playing."""
    st = _spotify_status()
    connected = bool(st.get("logged_in"))
    yt = dict(db.get("yt") or {})
    # mode = qué muestra la barra: spotify (dispositivo remoto) · youtube (audio oculto) · idle.
    mode = "spotify" if connected else ("youtube" if yt.get("videoId") else "idle")
    return {
        **_SEED,
        "connected": connected,
        "can_connect": bool(st.get("can_connect")),
        "own_client_id_set": bool(st.get("own_client_id_set")),
        "default_available": bool(st.get("default_available")),
        "redirect_uri": st.get("redirect_uri", ""),
        "now_playing": (_now_playing() if connected else None),
        "yt": yt,
        "mode": mode,
    }


def _derive_top(db: dict) -> list:
    """Más escuchadas = derivado de los contadores de reproducción (counts), orden desc por count."""
    counts = db.get("counts") or {}
    items = sorted(counts.values(), key=lambda c: (-int(c.get("count") or 0), _norm(c.get("title"))))
    return [dict(c) for c in items[:_TOP_CAP]]


def _compose(db: dict) -> dict:
    """El blob EXACTO que ve la tarjeta: db persistido + estado vivo + más-escuchadas derivadas."""
    return {**db, **_live_fields(db), "top": _derive_top(db)}


def view_data(q: str = "") -> dict:
    return _compose(_load_db())


def _persist(db: dict) -> None:
    """Guarda el compuesto (preserva yt + playlists + counts y refleja conexión) → dispara SSE = re-render."""
    try:
        store.save(WID, _compose(db))
    except Exception:
        pass


def _save_view() -> None:
    _persist(_load_db())


# ── modelo de tracks / listas ───────────────────────────────────────────────────────────────────────────────
def _track_query(t: dict) -> str:
    q = (t.get("query") or "").strip()
    if q:
        return q
    parts = [t.get("title") or "", t.get("artist") or ""]
    return " ".join(p for p in parts if p).strip() or (t.get("title") or "")


def _track_from_payload(p: dict) -> "dict | None":
    """Construye un track desde un payload flexible: {track:{...}} o {query|title[,artist,album]}."""
    src = p.get("track")
    if isinstance(src, dict):
        title = (src.get("title") or p.get("query") or "").strip()
        return {"title": title, "artist": (src.get("artist") or "").strip(),
                "album": (src.get("album") or "").strip(), "art": src.get("art") or "",
                "query": (src.get("query") or title).strip(), "uri": src.get("uri") or "",
                "videoId": src.get("videoId") or ""}
    q = (p.get("query") or (src if isinstance(src, str) else "") or p.get("title") or "").strip()
    if not q:
        return None
    title = (p.get("title") or q).strip()
    return {"title": title, "artist": (p.get("artist") or "").strip(),
            "album": (p.get("album") or "").strip(), "art": "", "query": q, "uri": "", "videoId": ""}


def _find_playlist(db: dict, ref) -> "dict | None":
    """Resuelve una referencia (id exacto o nombre en lenguaje natural) a la lista real. Nunca inventa."""
    ref = str(ref or "")
    pls = db.get("playlists") or []
    for pl in pls:                                    # id exacto
        if pl.get("id") == ref:
            return pl
    nref = _norm(ref)
    if not nref:
        return None
    for pl in pls:                                    # nombre exacto
        if _norm(pl.get("name")) == nref:
            return pl
    for pl in pls:                                    # contiene / contenido
        nn = _norm(pl.get("name"))
        if nn and (nref in nn or nn in nref):
            return pl
    return None


def _resolve_track_index(tracks: list, item) -> "int | None":
    """item = índice 1-based ('2') o texto que casa con el título/query de un track de la lista."""
    if item is None:
        return None
    s = str(item).strip()
    if s.isdigit():
        i = int(s) - 1
        return i if 0 <= i < len(tracks) else None
    nitem = _norm(s)
    if not nitem:
        return None
    for i, t in enumerate(tracks):                    # exacto
        if nitem == _norm(t.get("title")) or nitem == _norm(t.get("query")):
            return i
    for i, t in enumerate(tracks):                    # contiene
        hay = _norm(" ".join([t.get("title") or "", t.get("artist") or "", t.get("query") or ""]))
        if nitem in hay:
            return i
    return None


def _push_recent(db: dict, t: dict) -> None:
    """Registra una reproducción: recientes (dedup por título+artista, cap) + contador para 'más escuchadas'."""
    title = (t.get("title") or t.get("query") or "").strip()
    if not title:
        return
    artist = (t.get("artist") or "").strip()
    key = _norm(title + "|" + artist)
    rec = db.setdefault("recent", [])
    rec[:] = [x for x in rec if x.get("_k") != key]
    rec.insert(0, {"title": title, "artist": artist, "album": (t.get("album") or "").strip(),
                   "art": t.get("art") or "", "query": t.get("query") or title, "_k": key,
                   "at": int(time.time())})
    del rec[_RECENT_CAP:]
    counts = db.setdefault("counts", {})
    c = counts.get(key) or {"title": title, "artist": artist, "album": (t.get("album") or "").strip(),
                            "art": t.get("art") or "", "query": t.get("query") or title, "count": 0}
    c["count"] = int(c.get("count") or 0) + 1
    counts[key] = c


def _play_track(track: dict) -> "dict":
    """Reproduce UN track por el seam del conector (Spotify si hay cuenta, si no YouTube-audio). Fail-safe."""
    from connectors import music
    r = music.control("play", query=_track_query(track), uri=track.get("uri") or "")
    return {"ok": bool(getattr(r, "ok", False)), "message": getattr(r, "message", ""),
            "reason": getattr(r, "reason", "")}


# ── ref_index (V2-026): las listas son referenciables por voz por su NOMBRE ────────────────────────────────
def ref_index() -> list:
    try:
        db = _load_db()
    except Exception:
        return []
    out = []
    for pl in db.get("playlists") or []:
        n = len(pl.get("tracks") or [])
        out.append({"id": pl.get("id"), "label": pl.get("name") or pl.get("id"),
                    "field": "playlist", "hint": f"{n} canción{'es' if n != 1 else ''}"})
    return out


def apply_action(action: str, payload: dict = None) -> dict:
    p = payload or {}

    # ── conexión de Spotify (sin cambios respecto a V2-041) ──────────────────────────────────────────────
    if action == "connect":
        cid = (p.get("client_id") or "").strip()
        if cid:
            try:
                from config import credentials
                credentials.set_key("SPOTIFY_CLIENT_ID", cid)
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "error": f"credential_store:{e}"[:120]}
        try:
            from connectors.spotify import auth
            res = auth.begin_login()          # {ok, url} o {ok:False, error:'no_client_id'}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)[:120]}
        if not res.get("ok") and res.get("error") == "no_client_id":
            res["need_client_id"] = True      # el widget muestra el campo avanzado
        return res

    if action == "disconnect":
        try:
            from connectors.spotify import auth
            auth.disconnect()
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)[:120]}
        _save_view()
        return {"ok": True}

    if action == "refresh":
        _save_view()
        return {"ok": True}

    # ── LISTAS (V2-058, Fase 1) ──────────────────────────────────────────────────────────────────────────
    if action == "create_playlist":
        name = (p.get("name") or p.get("playlist") or "").strip() or "Nueva lista"
        db = _load_db()
        used = {pl.get("id") for pl in db["playlists"]}
        pid = _slug(name); base, i = pid, 2
        while pid in used:
            pid = f"{base}-{i}"; i += 1
        db["playlists"].append({"id": pid, "name": name, "art": "", "tracks": []})
        db["view"] = {"kind": "playlist", "id": pid}          # la pantalla se adapta a la lista nueva
        _persist(db)
        return {"ok": True, "playlist": pid, "name": name}

    if action == "add_to_playlist":
        db = _load_db()
        pl = _find_playlist(db, p.get("playlist") or p.get("id"))
        if pl is None:
            return {"ok": False, "error": "playlist_not_found", "playlist": p.get("playlist")}
        tr = _track_from_payload(p)
        if not tr:
            return {"ok": False, "error": "no_track"}
        pl.setdefault("tracks", []).append(tr)
        db["view"] = {"kind": "playlist", "id": pl["id"]}
        _persist(db)
        return {"ok": True, "playlist": pl["id"], "track": tr.get("title")}

    if action == "remove_from_playlist":
        db = _load_db()
        pl = _find_playlist(db, p.get("playlist") or p.get("id"))
        if pl is None:
            return {"ok": False, "error": "playlist_not_found", "playlist": p.get("playlist")}
        tracks = pl.get("tracks") or []
        idx = _resolve_track_index(tracks, p.get("item"))
        if idx is None:
            return {"ok": False, "error": "track_not_found", "item": p.get("item")}
        removed = tracks.pop(idx)
        db["view"] = {"kind": "playlist", "id": pl["id"]}
        _persist(db)
        return {"ok": True, "playlist": pl["id"], "removed": removed.get("title")}

    if action == "play_playlist":
        db = _load_db()
        pl = _find_playlist(db, p.get("playlist") or p.get("id"))
        if pl is None:
            return {"ok": False, "error": "playlist_not_found", "playlist": p.get("playlist")}
        tracks = pl.get("tracks") or []
        if not tracks:
            return {"ok": False, "error": "empty_playlist", "playlist": pl["id"]}
        try:
            r = _play_track(tracks[0])                          # la 1ª suena YA
            from connectors import music
            for t in tracks[1:]:                                # el resto a la cola (V2-047 F4)
                try:
                    music.control("queue", query=_track_query(t), uri=t.get("uri") or "")
                except Exception:
                    pass
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)[:120]}
        _push_recent(db, tracks[0])
        db["view"] = {"kind": "playlist", "id": pl["id"]}
        _persist(db)
        return {"ok": r.get("ok", False), "message": r.get("message", ""), "playlist": pl["id"]}

    if action == "open_view":
        kind = (p.get("kind") or "home").strip().lower()
        if kind not in ("home", "playlist", "album", "artist", "nowplaying"):
            kind = "home"
        db = _load_db()
        vid = str(p.get("id") or "").strip()
        if kind == "playlist" and vid:
            pl = _find_playlist(db, vid)                        # nombre → id real
            vid = pl["id"] if pl else vid
        db["view"] = {"kind": kind, "id": vid}
        _persist(db)
        return {"ok": True, "view": db["view"]}

    if action == "back":
        db = _load_db()
        db["view"] = {"kind": "home", "id": ""}
        _persist(db)
        return {"ok": True, "view": db["view"]}

    # ── control de reproducción (botones de la tarjeta). La voz usa play_music. Converge en el seam. ──────
    # `ended` (V2-047 F4): lo dispara el propio widget al terminar la canción → el seam avanza la cola.
    if action in ("play", "pause", "resume", "next", "previous", "volume_up", "volume_down", "set_volume",
                  "queue", "ended"):
        try:
            from connectors import music
            query = str(p.get("query") or "")
            r = music.control(action, query=query, percent=int(p.get("level") or 0))
            ok = bool(getattr(r, "ok", False))
            # reproducir un track suelto desde la tarjeta (recientes/más-escuchadas/fila de lista) alimenta
            # recientes + más-escuchadas. La voz (play_music) va por otro camino y no pasa por aquí (Fase 1).
            if action == "play" and ok and query:
                db = _load_db()
                _push_recent(db, {"title": query, "query": query})
                _persist(db)
            else:
                _save_view()
            return {"ok": ok, "message": getattr(r, "message", ""), "reason": getattr(r, "reason", "")}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)[:120]}

    return {"ok": False, "error": "unknown_action", "action": action}
