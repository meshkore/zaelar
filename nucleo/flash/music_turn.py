"""Play music from a turn: shared execution (V2-380).

This channel (`probe`, driven by the use cases) resolved `play_music` to the `music` label and stopped there:
no data ops, no live widget, and the turn replied “Done.”—a canned acknowledgement—for playback that did not exist.

Medido en la PRIMERA ronda que `play-music-and-build-playlist` ha tenido nunca (2026-08-27, **1/5**, el peor
del día): `familias faltantes: ['widget']`, cero operaciones de widget, y el turno inventando «Painkiller» de
Judas Priest y «Stairway to Heaven» para quien pedía música tranquila e instrumental. El juez lo archivó como
narrar una sesión ficticia. Lo era — y el caso no podía pasar POR CONSTRUCCIÓN, así que su nota no decía nada
del producto: estaba midiendo un mecanismo INALCANZABLE.

This is the third member of the same family in `probe.py`, and its code repeats the rule at every backstop: it is
the PARALLEL implementation of the voice provider, “wire both”. The same happened with cron tags (V2-121) and
login handoff (V2-176), whose remedy, `web_auth`, is this module’s template.

El rail es el MISMO que ejecuta la voz (`music_flow.run`), así que esto no añade una segunda forma de poner
música: la enchufa.
"""
from __future__ import annotations


def request_from(tool_calls: list) -> dict:
    """What `play_music` requested, normalized: `{action, query}`. `play` is the default because it is the action
    for most turns and an empty `action` must not remain unexecuted: that is the gap this module closes."""
    pm = next((t for t in (tool_calls or []) if t.get("name") == "play_music"), None) or {}
    args = pm.get("args") or {}
    return {"action": (str(args.get("action") or "play").strip().lower() or "play"),
            "query": str(args.get("query") or "").strip()}


async def execute(action: str, query: str) -> dict:
    """Pone (o controla) la música y devuelve el parte de lo que PASÓ, para que la boca no tenga que adivinar.

    `extract=None` a propósito: el 2º pase que resuelve una petición difusa lo presta el llamante, y en la voz
    es una llamada de modelo más. Aquí se mide el MECANISMO, no la resolución difusa, y una llamada extra por
    turno se paga en cada ronda del plató.

    Fail-soft entero: el turno tiene que salir aunque el reproductor esté roto.
    """
    try:
        from nucleo.flash import music_flow as _mflow
        res = await _mflow.run(action, query, extract=None)
        # The player CARD opens where the data lands (V2-463) - shared rail, same fix as its two siblings
        # (imagenes/youtube): the voice provider emits its own early show, the probe channel emitted none, so
        # probe rounds played music on a canvas with no card. Only on PLAY-like success: a stop/volume op on
        # an already-closed card must not reopen it.
        if bool(getattr(res, "ok", False)) and str(action or "").strip() not in ("stop", "pause", "close"):
            try:
                from voice.observer import emit as _emit
                _emit("widget", "show", extra={"id": "musica", "src": "flash"})
            except Exception:  # noqa: BLE001
                pass
        return {"executed": "play_music", "ok": bool(getattr(res, "ok", False)),
                "accion": action, "query": str(query or "")[:80],
                "message": str(getattr(res, "message", "") or "")[:160]}
    except Exception as e:  # noqa: BLE001
        return {"executed": "play_music", "ok": False, "execute_error": str(e)[:200]}


def spoken_for(parte: dict, ack: str) -> str:
    """Lo que se DICE tras intentar poner música. `ack` es el enlatado del idioma, solo para el caso bueno mudo.

    «Hecho.» sobre una reproducción que no existe es la cuarta vez que una frase enlatada nuestra es la que
    miente (V2-176 «Hecho.» sobre una tarea recién arrancada, V2-209 «Aquí lo tienes» sobre una tarjeta vacía,
    V2-377 «la tarea del navegador» sobre el encargo de otro).
    """
    parte = parte if isinstance(parte, dict) else {}
    if parte.get("executed") != "play_music":
        return ack
    msg = str(parte.get("message") or "").strip()
    if parte.get("ok"):
        return msg or ack
    return "No he podido ponerlo: " + (msg or "el reproductor no ha arrancado.")
