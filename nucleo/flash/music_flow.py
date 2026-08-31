"""nucleo/flash/music_flow.py — RESOLVE→VALIDATE→ACT of the music pipeline (V2-042, first instantiation of the pattern).

The operator does not always give the exact name ("play me that one that says 'fly with me'… I think it was by Sinatra"). The
pipeline is DETERMINISTIC and lives IN CODE (the FlashBrain remains non-reasoning; it only calls `play_music`):

  1. **act directly** — `music.control(play, query)`: provider search engines (Spotify/YouTube) are already
     tolerant of fuzziness; if they get it right, done (~1-2s).
  2. **resolve** — if `no_track`: web search using the **WARM Chromium** from startup (`nucleo/websearch`,
     V2-024 prewarm) → "song <track>".
  3. **validate/extract** — 2nd pass of the SAME model already paid for by the turn (`web_search` pattern): from the snippets,
     extract the canonical `Artist - Title` (or NO if it is unclear). The caller PROVIDES the extractor (async) — this
     module does not know the model client (testable).
  4. **act again** — `music.control(play, canonical)`. The spoken confirmation says WHAT is playing (validation by
     announcement: if it was not the intended one, the operator corrects it and that turn retries with more data).

All attempt state lives in the `music.search` rail run (`nucleo/rails.py`): searching → resolved
(disappears) or ISOLATED `sin_resolver` with the track and attempts — the next turn ("it was by Sinatra") sees it in
the prompt and retries with the enriched query. What is PLAYING lives in the `music.playing` run, and each
playback is WRITTEN TO MEMORY (`memory.ingest_message(source="music", entity=artist)`) → history + preferences
(`recent_by_source("music")` + retriever recall: "play something I like").

I/O ALWAYS off-loop (`asyncio.to_thread`, V2-011). Fail-safe: never raises into the voice turn.
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
    """`Artist - Title` from the extractor response; '' if it said NO / was malformed."""
    line = (reply or "").strip().splitlines()[0].strip().strip('"«»') if (reply or "").strip() else ""
    if not line or line.upper().startswith("NO"):
        return ""
    return line if (" - " in line or " — " in line) else ""


def _remember_play(res, query: str) -> None:
    """Writes playback to MEMORY (via the typed path, off-loop): music history + preferences. Best-effort."""
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
    """Updates activities + memory after successful playback (off-loop)."""
    from nucleo import rails as acts
    acts.resolve("music.search")
    t = getattr(res, "track", None)
    label = t.label() if t is not None and hasattr(t, "label") else (query or "música")
    acts.upsert("music.playing", label, status="playing",
                detail=f"vía {getattr(res, 'provider', '') or '?'}")
    if getattr(res, "action", "") == "play" and t is not None:
        _remember_play(res, query)


def _on_control(res, action: str) -> None:
    """Reflects pauses/resumptions/queueing in the `music.playing` activity (if it exists). Off-loop."""
    from nucleo import rails as acts
    if action == "queue":
        # V2-047 F4: the queue is visible in the live run (for the prompt and viewer) — how many remain to play.
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
    """Executes ONE music action with fuzzy resolution. Returns the final `MusicResult` (with an extra `.resolved_from`
    if a chain occurred). `extract(system, user) -> str` = async 2nd model pass, provided by the caller (None =
    no resolution, direct attempt only)."""
    from connectors import music

    # 1 · ACT DIRECTLY (provider search engines already tolerate fuzziness)
    res = await asyncio.to_thread(music.control, action, query, "", 0, "")
    if getattr(res, "ok", False):
        # 'ended' (queue advancement) brings a NEW track into playback → refresh music.playing as a play.
        if action in ("play", "ended") and not (getattr(res, "extra", {}) or {}).get("noop"):
            await asyncio.to_thread(_on_success, res, query)
        else:
            await asyncio.to_thread(_on_control, res, action)
        return res

    # only fuzzy playback enters the web-resolution chain. 'queue'/'ended' are not "resolved" by searching;
    # neither is a failed pause. Only a play with a query and no_track.
    if action != "play" or not (query or "").strip() or getattr(res, "reason", "") != "no_track" or extract is None:
        return res

    from nucleo import rails as acts
    await asyncio.to_thread(acts.upsert, "music.search", query.strip(), status="searching", bump=True)

    # 2 · RESOLVE — websearch (warm Chromium from prewarm; falls back in layers if unavailable)
    try:
        from nucleo import websearch
        web = await asyncio.to_thread(websearch.search, f"canción {query}")
        ctx = websearch.format_results(web)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"music_flow: websearch falló: {e!r}")
        ctx = ""

    # 3 · VALIDATE/EXTRACT — 2nd pass of the turn's model (strict format 'Artist - Title' | NO)
    canonical = ""
    if ctx:
        try:
            reply = await extract(_EXTRACT_SYS, f"PISTA: {query}\n\nRESULTADOS DE BÚSQUEDA:\n{ctx}")
            canonical = _parse_canonical(reply)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"music_flow: extractor falló: {e!r}")

    # 4 · ACT AGAIN with the canonical name
    if canonical:
        res2 = await asyncio.to_thread(music.control, "play", canonical, "", 0, "")
        if getattr(res2, "ok", False):
            await asyncio.to_thread(_on_success, res2, query)
            try:
                res2.extra["resolved_from"] = query.strip()   # the caller announces WHAT is playing (validation by announcement)
            except Exception:
                pass
            return res2

    # unresolved → the activity remains ISOLATED (with the track + attempts) to resume with more data
    await asyncio.to_thread(acts.fail, "music.search",
                            f"probado: {canonical}" if canonical else "la web no la identificó")
    try:
        res.message = _ASK_MORE[_lang()]
    except Exception:
        pass
    return res
