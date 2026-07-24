#
# youtube — reproductor de YouTube EMBEBIDO en el canvas (un <iframe> real que REPRODUCE, no una captura).
# El vídeo se controla por VOZ: el FlashBrain llama a apply_action (tool widget_data) y aquí guardamos el
# ESTADO/comando deseado en el store; el cliente (widget.js) lo aplica al reproductor por postMessage (YouTube
# IFrame API, SIN librería). data.py es servidor puro (stdlib) — nunca toca el reproductor.
#
import re
import urllib.parse
import urllib.request

from .. import store

WID = "youtube"

# Semilla: reproductor EN BLANCO por defecto (sin vídeo) hasta que el operador pida uno.
_SEED = {
    "videoId": "",
    "title": "",
    "url": "",
    "channel": "",
    "published": "",
    "latest": False,
    "volume": 70,
    "muted": True,      # el autoplay del navegador exige empezar en silencio; "quita el silencio" para oírlo
    "paused": True,
    "last_cmd": "",
    "cmd_seq": 0,
    "loading": False,     # V2-062 fix: la búsqueda de "load" tarda unos segundos (red); sin esto la tarjeta se
    "loading_query": "",  # veía TOTALMENTE vacía sin ninguna señal de que algo estaba pasando (bug real 2026-07-23).
}

_YT_RE = re.compile(
    r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/shorts/)([0-9A-Za-z_-]{11})"
)


def _extract_id(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    m = _YT_RE.search(s)
    if m:
        return m.group(1)
    if re.fullmatch(r"[0-9A-Za-z_-]{11}", s):          # ya es un id pelado
        return s
    return ""


# Pide el vídeo MÁS RECIENTE (p. ej. "el último vídeo de José Luis Cárpatos") → orden por fecha de subida.
_LATEST_RE = re.compile(r"\b(?:[uú]ltim[oa]s?|m[aá]s\s+recientes?|reciente|nuevo|last|latest|newest)\b", re.I)


def _unesc(s: str) -> str:
    """Decodifica los \\uXXXX que YouTube a veces embebe en el JSON, sin tocar el UTF-8 ya decodificado."""
    return re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), s or "")


def _search_id(q: str) -> dict:
    """Best-effort: resuelve una frase ("el gol de Messi") al primer vídeo de YouTube. Stdlib, 6s, fail-open.
    Si la frase pide el vídeo MÁS RECIENTE de alguien ("el último de …"), ordena por fecha de subida.
    Devuelve {videoId,title,channel,published,latest} — la fecha de publicación permite VERIFICAR que es el
    vídeo correcto (V2-057: no ejecutar a ciegas; entregar un resultado comprobable de un vistazo)."""
    q = (q or "").strip()
    out = {"videoId": "", "title": "", "channel": "", "published": "", "latest": False}
    if not q:
        return out
    latest = bool(_LATEST_RE.search(q))
    out["latest"] = latest
    try:
        url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(q)
        if latest:                                       # ordenar por fecha de subida (sp=CAI%3D)
            url += "&sp=CAI%3D"
        req = urllib.request.Request(url, headers={
            "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"),
            "Accept-Language": "es-ES,es;q=0.9",
        })
        html = urllib.request.urlopen(req, timeout=6).read().decode("utf-8", "ignore")
        m = re.search(r'"videoId":"([0-9A-Za-z_-]{11})"', html)
        if not m:
            return out
        vid = m.group(1)
        out["videoId"] = vid
        # Bloque del videoRenderer de ESTE vídeo: de ahí sacamos título, canal y fecha de publicación.
        blk = html[m.start(): m.start() + 2500]
        t = re.search(r'"title":\{"runs":\[\{"text":"([^"]{2,140})"', blk) \
            or re.search(r'"videoId":"' + re.escape(vid) + r'".*?"text":"([^"]{3,120})"', html)
        out["title"] = _unesc(t.group(1)) if t else q
        ch = re.search(r'"(?:ownerText|longBylineText)":\{"runs":\[\{"text":"([^"]{1,80})"', blk)
        out["channel"] = _unesc(ch.group(1)) if ch else ""
        pub = re.search(r'"publishedTimeText":\{"simpleText":"([^"]{2,40})"', blk)
        out["published"] = _unesc(pub.group(1)) if pub else ""
        return out
    except Exception:
        return out


def _load() -> dict:
    db = store.load(WID, dict(_SEED))
    for k, v in _SEED.items():                          # normaliza campos ausentes (store antiguo)
        db.setdefault(k, v)
    return db


def view_data(q: str = "") -> dict:
    try:
        return _load()
    except Exception as e:
        return {**_SEED, "error": str(e)[:120]}


def _bump(db: dict, cmd: str) -> dict:
    db["last_cmd"] = cmd
    db["cmd_seq"] = int(db.get("cmd_seq") or 0) + 1
    store.save(WID, db)
    return {"ok": True, "cmd": cmd, "videoId": db.get("videoId"), "title": db.get("title"),
            "volume": db.get("volume"), "muted": db.get("muted"), "paused": db.get("paused")}


def apply_action(action: str, payload: dict = None) -> dict:
    p = payload or {}
    db = _load()

    if action == "load":
        raw = str(p.get("url") or p.get("videoId") or "").strip()
        vid = _extract_id(raw)
        title = str(p.get("title") or "").strip()
        channel, published, latest = "", "", False
        if not vid:                                     # no era URL/id → buscar por nombre
            q = str(p.get("query") or p.get("q") or raw or "").strip()
            # LOADER real (bug 2026-07-23, "no hay ningún loader que indique que estás buscando"): _search_id
            # scrapea la red (varios segundos) — sin esto la tarjeta se veía TOTALMENTE vacía mientras tanto,
            # indistinguible de "no hay nada pedido". Guarda+emite YA (antes de la red) para que widget.js pinte
            # el spinner de inmediato; el load final lo apaga.
            db["loading"], db["loading_query"] = True, q
            store.save(WID, db)
            r = _search_id(q)
            vid = r["videoId"]
            latest = r["latest"]
            if vid and not title:
                title = r["title"]
            channel, published = r["channel"], r["published"]
        db["loading"], db["loading_query"] = False, ""
        if not vid:
            store.save(WID, db)                          # apaga el loader aunque no se encontrara nada
            return {"ok": False, "error": "no_video", "message": "No encontré ese vídeo."}
        db["videoId"] = vid
        db["url"] = "https://www.youtube.com/watch?v=" + vid
        db["title"] = title or db["url"]
        db["channel"] = channel                          # V2-057: metadatos VERIFICABLES en la tarjeta
        db["published"] = published                      # p. ej. "hace 2 días" — confirma que es el correcto
        db["latest"] = latest                            # se pidió el más reciente (orden por fecha)
        db["paused"] = False
        return _bump(db, "load")

    if action == "play":
        db["paused"] = False
        return _bump(db, "play")
    if action == "pause":
        db["paused"] = True
        return _bump(db, "pause")
    if action == "mute":
        db["muted"] = True
        return _bump(db, "mute")
    if action == "unmute":
        db["muted"] = False
        return _bump(db, "unmute")
    if action == "volume_up":
        db["volume"] = min(100, int(db.get("volume") or 70) + 15)
        db["muted"] = False
        return _bump(db, "volume_up")
    if action == "volume_down":
        db["volume"] = max(0, int(db.get("volume") or 70) - 15)
        return _bump(db, "volume_down")
    if action == "set_volume":
        try:
            lvl = int(p.get("level"))
        except (TypeError, ValueError):
            return {"ok": False, "error": "bad_level", "message": "Dime un nivel entre 0 y 100."}
        db["volume"] = max(0, min(100, lvl))
        db["muted"] = db["volume"] == 0
        return _bump(db, "set_volume")
    if action == "restart":
        db["paused"] = False
        return _bump(db, "restart")
    if action == "close":
        # Vacía el vídeo → widget.js detecta videoId="" y RECONSTRUYE la tarjeta sin <iframe>: el vídeo deja de
        # reproducirse DE VERDAD en el navegador (no es solo borrar datos), y la tarjeta pasa al estado vacío.
        db["videoId"] = ""
        db["title"] = ""
        db["url"] = ""
        db["channel"] = ""
        db["published"] = ""
        db["latest"] = False
        db["paused"] = True
        db["muted"] = True
        return _bump(db, "close")

    return {"ok": False, "error": "unknown_action", "action": action}
