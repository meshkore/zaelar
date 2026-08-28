"""Which SHEET belongs to an errand — the one question V2-432 turned out to hinge on.

Extracted from `live_blocks` on 2026-08-28, and not to dodge a line count: the architecture ratchet fired
while instrumenting this resolution, and it was right to. Resolving the errand's box is a subject of its own —
it has two paths, it is read by three different callers, and when it fails it fails MUTE, which is exactly the
defect measured that night (45 of the 48 rounds whose sheet had named rows had turns where the live block told
the model the task was stalled).

A file that is about one thing can say what it is about. Inside `live_blocks` this was a helper among twenty.
"""
from __future__ import annotations


def _sheet_of_tab(nav_task_id: str) -> str:
    """La hoja de este encargo, resuelta como la resuelve QUIEN ESCRIBE (V2-352).

    Hay dos caminos y el escritor (`navegador.act_api._sheet_for`, que alimenta `_hand_over`) usa los dos:

      1. el SELLO de la pestaña — durable, sobrevive a que al worker le releven o se muera, que es justo cuando
         más falta hace (V2-281). Pero **se escribe una sola vez, en `tasks.create()`**: si el registro aún no
         tenía hoja sellada en ese instante, queda vacío PARA SIEMPRE, y el propio comentario de `create` lo
         avisa. Ese cero es también la «tarjeta fantasma» que el arnés reporta: sin hoja resuelta, los hallazgos
         caen en la caja `results` desnuda, la que no es de nadie.
      2. el REGISTRO de sesiones vivas — sabe contestar mientras el worker viva.

    Los LECTORES se paraban en el primero, y eso les dejaba ciegos justo en la ronda que lo destapó: medido en
    `search-buy-used-car` ronda 12 (1/5), el backstop de entrega emitió su silencio NUEVE veces con `rows=0`
    mientras la hoja tenía DOCE coches con nombre, precio y enlace — escritos por el camino 2, ilegibles por el
    1. El operador preguntó cinco veces «¿ya tienes algo?» y oyó cinco negativas.

    El ORDEN no cambia y es deliberado: sello primero, registro de RESPALDO. Ni más ni menos que el escritor.
    """
    try:
        from widgets.navegador import tasks as _t
        sello = str(((_t.get(str(nav_task_id)) or {}).get("sheet")) or "").strip()
        if sello:
            return sello
    except Exception:  # noqa: BLE001
        pass
    try:
        from nucleo import dispatch as _disp
        _reg = str(_disp.sheet_for_nav_task(str(nav_task_id)) or "").strip()
    except Exception:  # noqa: BLE001
        _reg = ""
    if not _reg:
        # NI SELLO NI REGISTRO, y sin decirlo el fallo es MUDO: se devuelve "" y el prompt se compone como si
        # no hubiera nada, indistinguible de que no lo haya. Firma de V2-432. Aquí porque los dos mueren acá.
        try:
            from voice.observer import emit
            emit("perf", "🧾 hoja del encargo SIN RESOLVER", role="system", extra={"nav_task": str(nav_task_id)})
        except Exception:  # noqa: BLE001 — instrumentar no puede tumbar el prompt
            pass
    return _reg
