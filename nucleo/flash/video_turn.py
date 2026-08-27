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


def request_from(tool_calls: list) -> dict:
    """Lo que pidió `play_video`, normalizado: `{query}`."""
    pv = next((t for t in (tool_calls or []) if t.get("name") == "play_video"), None) or {}
    return {"query": str((pv.get("args") or {}).get("query") or "").strip()}


async def execute(query: str) -> dict:
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
        res = await brain_action("youtube", "load", {"query": q} if q else {})
        res = res if isinstance(res, dict) else {}
        return {"executed": "play_video", "ok": bool(res.get("ok", res.get("videoId"))),
                "query": q[:80], "videoId": str(res.get("videoId") or ""),
                "title": str(res.get("title") or "")[:120],
                "message": str(res.get("message") or res.get("error") or "")[:160]}
    except Exception as e:  # noqa: BLE001
        return {"executed": "play_video", "ok": False, "query": q[:80], "execute_error": str(e)[:200]}


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
    if parte.get("ok"):
        t = str(parte.get("title") or "").strip()
        return f"Ya lo tienes en pantalla: «{t}»." if t else ack
    msg = str(parte.get("message") or "").strip()
    return "No he podido ponerlo: " + (msg or "no encontré ese vídeo.")
