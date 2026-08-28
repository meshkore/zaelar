"""Poner música desde un turno: la ejecución, compartida (V2-380).

Este canal (`probe`, el que conducen los casos de uso) resolvía `play_music` a la etiqueta «music» y ahí
acababa todo: cero data-ops, cero widget vivo, y el turno contestaba «Hecho.» —el ack enlatado— sobre una
reproducción que no existía.

Medido en la PRIMERA ronda que `play-music-and-build-playlist` ha tenido nunca (2026-08-27, **1/5**, el peor
del día): `familias faltantes: ['widget']`, cero operaciones de widget, y el turno inventando «Painkiller» de
Judas Priest y «Stairway to Heaven» para quien pedía música tranquila e instrumental. El juez lo archivó como
narrar una sesión ficticia. Lo era — y el caso no podía pasar POR CONSTRUCCIÓN, así que su nota no decía nada
del producto: estaba midiendo un mecanismo INALCANZABLE.

Tercera vez de la misma familia en `probe.py`, y su propio código lo repite en cada backstop: es la
implementación PARALELA del provider de voz, «cablear en AMBOS». Ya pasó con las tags de cron (V2-121) y con
el traspaso de login (V2-176) — cuyo remedio, `web_auth`, es el molde de este módulo.

El rail es el MISMO que ejecuta la voz (`music_flow.run`), así que esto no añade una segunda forma de poner
música: la enchufa.
"""
from __future__ import annotations


def request_from(tool_calls: list) -> dict:
    """Lo que pidió `play_music`, normalizado: `{action, query}`. `play` es el defecto porque es la acción de
    la inmensa mayoría de los turnos y porque un `action` vacío no puede quedarse sin ejecutar: sería el
    defecto que este módulo cierra, con otra cara."""
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
