"""nucleo/flash/music_flow.py — cadena RESOLVER→VALIDAR→ACTUAR de la música (V2-042, 1ª instanciación del patrón).

El operador no siempre da el nombre exacto ("ponme esa que dice 'vuela conmigo'… creo que era de Sinatra"). La
cadena es DETERMINISTA y vive EN CÓDIGO (el FlashBrain sigue no-razonador; él solo llama a `play_music`):

  1. **actuar directo** — `music.control(play, query)`: los buscadores de los proveedores (Spotify/YouTube) ya son
     tolerantes a lo difuso; si aciertan, listo (~1-2s).
  2. **resolver** — si `no_track`: búsqueda web con el **Chromium CALIENTE** del arranque (`nucleo/websearch`,
     prewarm V2-024) → "canción <pista>".
  3. **validar/extraer** — 2º pase del MISMO modelo que el turno ya paga (patrón de `web_search`): de los snippets
     extrae `Artista - Título` canónico (o NO si no está claro). El caller PRESTA el extractor (async) — este
     módulo no conoce el cliente del modelo (testeable).
  4. **re-actuar** — `music.control(play, canónico)`. La confirmación hablada dice QUÉ suena (validación por
     anuncio: si no era, el operador corrige y ese turno reintenta con más datos).

Todo el estado del intento vive en el run del rail `music.search` (`nucleo/rails.py`): buscando → resuelto
(desaparece) o `sin_resolver` AISLADO con la pista y los intentos — el siguiente turno ("era de Sinatra") lo ve en
el prompt y reintenta con la query enriquecida. Lo que SUENA vive en el run `music.playing`, y cada
reproducción se VUELCA A MEMORIA (`memory.ingest_message(source="music", entity=artista)`) → historial + gustos
(`recent_by_source("music")` + recall del retriever: "pon algo que me guste").

I/O SIEMPRE off-loop (`asyncio.to_thread`, V2-011). Fail-safe: nunca lanza al turno de voz.
"""
from __future__ import annotations

import asyncio

from loguru import logger

_EXTRACT_SYS = (
    "Eres un identificador de canciones. Con la PISTA del usuario y los RESULTADOS de búsqueda, identifica la "
    "canción concreta. Responde SOLO con el formato exacto `Artista - Título` (una línea, nada más, sin comillas "
    "ni explicación). Si los resultados no permiten identificarla con claridad, responde exactamente NO."
)

_ASK_MORE = {
    "es": "No he dado con esa canción. ¿Me dices el artista o alguna palabra más de la letra?",
    "en": "I couldn't pin down that song. Can you give me the artist or a few more words from the lyrics?",
}


def _lang() -> str:
    try:
        from voice.engine.core import langs
        code = (langs.current_code() or "es").lower()
        return code if code in _ASK_MORE else "es"
    except Exception:
        return "es"


def _parse_canonical(reply: str) -> str:
    """`Artista - Título` de la respuesta del extractor; '' si dijo NO / vino sucio."""
    line = (reply or "").strip().splitlines()[0].strip().strip('"«»') if (reply or "").strip() else ""
    if not line or line.upper().startswith("NO"):
        return ""
    return line if (" - " in line or " — " in line) else ""


def _remember_play(res, query: str) -> None:
    """Vuelca la reproducción a la MEMORIA (vía tipada, off-loop): historial musical + gustos. Best-effort."""
    try:
        t = getattr(res, "track", None)
        if t is None:
            return
        title = (t.title or "").strip()
        artist = (t.artist or "").strip()
        if not title:
            return
        body = f"Sonó «{title}»" + (f" de {artist}" if artist else "")
        if (query or "").strip() and query.strip().lower() not in title.lower():
            body += f" (la pidió como: «{query.strip()}»)"
        from memory import api as memory
        memory.ingest_message(source="music", entity=artist or getattr(res, "provider", "") or "music",
                              text=body, trust="operator", durable=True, concepts=["música"])
    except Exception as e:  # noqa: BLE001
        logger.debug(f"music_flow._remember_play saltado: {e!r}")


def _on_success(res, query: str) -> None:
    """Actualiza actividades + memoria tras una reproducción OK (off-loop)."""
    from nucleo import rails as acts
    acts.resolve("music.search")
    t = getattr(res, "track", None)
    label = t.label() if t is not None and hasattr(t, "label") else (query or "música")
    acts.upsert("music.playing", label, status="playing",
                detail=f"vía {getattr(res, 'provider', '') or '?'}")
    if getattr(res, "action", "") == "play" and t is not None:
        _remember_play(res, query)


def _on_control(res, action: str) -> None:
    """Refleja pausas/reanudaciones/cola en la actividad `music.playing` (si existe). Off-loop."""
    from nucleo import rails as acts
    if action == "queue":
        # V2-047 F4: la cola se ve en el run vivo (para el prompt y el visor) — cuántas quedan por sonar.
        cur = acts.get("music.playing")
        n = int((getattr(res, "extra", {}) or {}).get("queue_len") or 0)
        if cur is not None:
            acts.upsert("music.playing", detail=(f"cola: {n} en espera" if n else cur.get("detail", "")))
        return
    cur = acts.get("music.playing")
    if not cur:
        return
    if action in ("pause", "stop"):
        acts.upsert("music.playing", status="paused")
    elif action == "resume":
        acts.upsert("music.playing", status="playing")


async def run(action: str, query: str, *, extract=None):
    """Ejecuta UNA acción de música con resolución difusa. Devuelve el `MusicResult` final (con `.resolved_from`
    extra si hubo cadena). `extract(system, user) -> str` = 2º pase async del modelo, lo presta el caller (None =
    sin resolución, solo el intento directo)."""
    from connectors import music

    # 1 · ACTUAR directo (los buscadores de proveedor ya toleran lo difuso)
    res = await asyncio.to_thread(music.control, action, query, "", 0, "")
    if getattr(res, "ok", False):
        # 'ended' (avance de cola) trae una pista NUEVA sonando → refresca music.playing como un play.
        if action in ("play", "ended") and not (getattr(res, "extra", {}) or {}).get("noop"):
            await asyncio.to_thread(_on_success, res, query)
        else:
            await asyncio.to_thread(_on_control, res, action)
        return res

    # solo la reproducción difusa entra en la cadena de resolución web. 'queue'/'ended' no se "resuelven" buscando;
    # un pause fallido tampoco. Solo un play con query y no_track.
    if action != "play" or not (query or "").strip() or getattr(res, "reason", "") != "no_track" or extract is None:
        return res

    from nucleo import rails as acts
    await asyncio.to_thread(acts.upsert, "music.search", query.strip(), status="searching", bump=True)

    # 2 · RESOLVER — websearch (Chromium caliente del prewarm; cae por capas si no)
    try:
        from nucleo import websearch
        web = await asyncio.to_thread(websearch.search, f"canción {query}")
        ctx = websearch.format_results(web)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"music_flow: websearch falló: {e!r}")
        ctx = ""

    # 3 · VALIDAR/EXTRAER — 2º pase del modelo del turno (formato estricto 'Artista - Título' | NO)
    canonical = ""
    if ctx:
        try:
            reply = await extract(_EXTRACT_SYS, f"PISTA: {query}\n\nRESULTADOS DE BÚSQUEDA:\n{ctx}")
            canonical = _parse_canonical(reply)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"music_flow: extractor falló: {e!r}")

    # 4 · RE-ACTUAR con el nombre canónico
    if canonical:
        res2 = await asyncio.to_thread(music.control, "play", canonical, "", 0, "")
        if getattr(res2, "ok", False):
            await asyncio.to_thread(_on_success, res2, query)
            try:
                res2.extra["resolved_from"] = query.strip()   # el caller anuncia QUÉ suena (validación por anuncio)
            except Exception:
                pass
            return res2

    # sin resolver → la actividad queda AISLADA (con la pista + intentos) para retomarla con más datos
    await asyncio.to_thread(acts.fail, "music.search",
                            f"probado: {canonical}" if canonical else "la web no la identificó")
    try:
        res.message = _ASK_MORE[_lang()]
    except Exception:
        pass
    return res
