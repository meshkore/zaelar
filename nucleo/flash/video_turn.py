"""Poner un vídeo desde un turno: la ejecución, compartida (V2-383).

Hermano exacto de `music_turn` (V2-380) y por la misma razón. En este canal (`probe`, el que conducen los
casos de uso) `play_video` resolvía a la etiqueta «canvas:show:youtube» y ahí acababa: cero data-ops, cero
`load`, el widget abierto y PELADO. El provider de voz sí lo ejecuta —muestra el widget y despacha `load` con
la query— y este canal es su implementación PARALELA: «cablear en AMBOS».

Medido en `watch-a-video-not-listen-to-it` (2026-08-27 12:53, **1/5**): ocho turnos pidiendo el tráiler de
Dune, cuatro veces la misma frase —«Te lo abro, aunque de momento está vacío»— hasta que el tester escribió
«eso me lo has dicho ya tres veces». Y la parte que más duele: el sistema SÍ encontró los tráileres. Seis
búsquedas, títulos reales («Dune: Part Two | Official Trailer»), todos a la hoja de resultados. Ninguno al
reproductor. La frase no era enlatada nuestra: era el modelo diciendo la verdad sobre una caja vacía.

El buscador tampoco estaba roto — `_search_id('Dune tráiler oficial')` resuelve hoy a `mSY_NbSmaUI`,
«Dune - Tráiler Oficial» de Warner Bros. España. Estaba INALCANZABLE desde este canal, que es la cuarta vez de
esta familia en `probe.py`: tags de cron (V2-121), traspaso de login (V2-176), música (V2-380) y ahora vídeo.
"""
from __future__ import annotations


def normalize_action(raw) -> str:
    """`play_video.action` → "play" | "list". ONE definition shared by BOTH channels (voice and probe): the
    V2-380/383 lesson is that anything decided per-channel ends up diverging per-channel. "list" is the V2-402
    half: a content search meant for CHOOSING ("find me videos about…") fills the player's list with several
    candidates without playing — a media search's destination is its dedicated widget, not the results sheet."""
    a = str(raw or "").strip().lower()
    return "list" if a in ("list", "lista", "search", "browse", "buscar", "varios") else "play"


def voice_dispatch(raw_action) -> "tuple[str, str]":
    """(data-op, observability label) for a play_video call — the voice provider's whole branch body, kept
    here so the search-vs-load decision cannot diverge from the probe channel's (V2-402)."""
    if normalize_action(raw_action) == "list":
        return "search", "🔎 vídeos → lista youtube"
    return "load", "▶️ vídeo → widget youtube"


def request_from(tool_calls: list) -> dict:
    """What `play_video` asked for, normalized: `{query, action}`."""
    pv = next((t for t in (tool_calls or []) if t.get("name") == "play_video"), None) or {}
    args = pv.get("args") or {}
    return {"query": str(args.get("query") or "").strip(),
            "action": normalize_action(args.get("action"))}


async def execute(query: str, action: str = "play") -> dict:
    """Carga el vídeo y devuelve el parte de lo que PASÓ, para que la boca no tenga que adivinar.

    Mismo rail que la voz (`brain_action` → `apply_action` del widget), no una segunda forma de poner vídeos.
    Se llama a `brain_action` y no a `dispatch_tag` a propósito: `dispatch_tag` se traga el resultado y
    devuelve `None`, o sea que con él no hay forma de saber si cargó — y no saberlo es exactamente cómo se
    acaba diciendo «te lo abro» sobre una pantalla vacía.

    Fail-soft entero: el turno tiene que salir aunque el reproductor esté roto.
    """
    q = str(query or "").strip()
    try:
        from widgets.server_api import brain_action
        if normalize_action(action) == "list":
            # V2-402 — a media search goes to the PLAYER: several candidates into the list, nothing autoplays.
            res = await brain_action("youtube", "search", {"query": q} if q else {})
            res = res if isinstance(res, dict) else {}
            _show_card(bool(res.get("ok")))
            return {"executed": "play_video", "accion": "list", "ok": bool(res.get("ok")),
                    "query": q[:80], "added": [str(t)[:120] for t in (res.get("added") or [])],
                    "count": int(res.get("count") or 0),
                    "message": str(res.get("message") or res.get("error") or "")[:160]}
        res = await brain_action("youtube", "load", {"query": q} if q else {})
        res = res if isinstance(res, dict) else {}
        _show_card(bool(res.get("ok", res.get("videoId"))))
        return {"executed": "play_video", "ok": bool(res.get("ok", res.get("videoId"))),
                "query": q[:80], "videoId": str(res.get("videoId") or ""),
                "title": str(res.get("title") or "")[:120],
                "message": str(res.get("message") or res.get("error") or "")[:160]}
    except Exception as e:  # noqa: BLE001
        return {"executed": "play_video", "ok": False, "query": q[:80], "execute_error": str(e)[:200]}


def _show_card(loaded: bool) -> None:
    """The player CARD opens where the data lands (V2-463) - shared rail, so the probe channel gets it too.

    The voice provider emits its own early show for instant feedback (idempotent on the frontend); this one
    is the guarantee. Found via the imagenes sibling: a measured round filled the widget while the operator
    watched a canvas where no card ever appeared - and this player had the exact same hole on the probe side.
    """
    if not loaded:
        return
    try:
        from voice.observer import emit as _emit
        _emit("widget", "show", extra={"id": "youtube", "src": "flash"})
    except Exception:  # noqa: BLE001
        pass


def spoken_for(parte: dict, ack: str) -> str:
    """Lo que se DICE tras intentar poner el vídeo. `ack` es el enlatado del idioma, solo para el caso bueno mudo.

    Se NOMBRA el vídeo que cargó, no «hecho»: es lo que deja al operador verificar de un vistazo que es el que
    pedía (V2-057), y es la diferencia entre entregar y afirmar que se entregó. Y si no cargó se dice que no
    cargó — quinta vez que una frase nuestra sobre una caja vacía es la que miente (V2-176, V2-209, V2-377,
    V2-380).
    """
    parte = parte if isinstance(parte, dict) else {}
    if parte.get("executed") != "play_video":
        return ack
    # THE ENGINE'S LANGUAGE, not Spanish (V2-464): same hole its imagenes sibling was caught with live on
    # the US agent — every canned line here was Spanish on an English-only engine. One read decides the set.
    en = _lang() == "en"
    if parte.get("accion") == "list":
        # A search is NAMED like the single video is: how many and which, verifiable at a glance (V2-057) —
        # and it invites a choice, because choosing is exactly what asking to SEARCH (vs to PLAY) means.
        if parte.get("ok"):
            added = [str(t) for t in (parte.get("added") or []) if str(t).strip()]
            if added:
                nombres = " · ".join(f"«{t}»" for t in added[:3])
                return (f"I've queued {len(added)} videos: {nombres}… tell me which one to play."
                        if en else
                        f"Te he puesto {len(added)} vídeos en la lista: {nombres}… dime cuál pongo.")
            return ("They were all in the list already — tell me which one to play." if en
                    else "Ya estaban todos en la lista — dime cuál pongo.")
        msg = str(parte.get("message") or "").strip()
        if en:
            return "I couldn't search for them: " + (msg or "I found no videos of that.")
        return "No he podido buscarlos: " + (msg or "no encontré vídeos de eso.")
    if parte.get("ok"):
        t = str(parte.get("title") or "").strip()
        if not t:
            return ack
        return f"It's up on your screen: «{t}»." if en else f"Ya lo tienes en pantalla: «{t}»."
    msg = str(parte.get("message") or "").strip()
    if en:
        return "I couldn't play it: " + (msg or "I found no such video.")
    return "No he podido ponerlo: " + (msg or "no encontré ese vídeo.")


def _lang() -> str:
    """`en` or `es` — the engine's own language (monolingual per process, `voice/engine/core/langs`)."""
    try:
        from voice.engine.core import langs
        code = (langs.current_code() or "es").lower()
        return "en" if code.startswith("en") else "es"
    except Exception:  # noqa: BLE001
        return "es"
