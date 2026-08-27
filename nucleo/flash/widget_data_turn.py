"""Ejecutar una data-op de widget desde un turno (extraído de `probe.py`, V2-383).

No cambia nada de lo que hacía: sale de `probe.py` porque es la MISMA preocupación que `music_turn` y
`video_turn` —un turno que ejecuta una operación de widget por el rail de la voz— y porque `probe.py` es un
fichero-dios con trinquete, así que meter la ejecución del vídeo obliga a sacar de él lo que ya no le
pertenece. La historia del bloque, que es la que explica por qué existe, viaja con él:

EJECUCIÓN REAL de una data-op (2026-07-25): sin esto el probe validaba el ROUTING pero nunca ENVIABA —
imposible reproducir e2e «manda a zalo …». Si la acción es FAST se despacha por el MISMO camino que la voz
(`widgets.dispatch_tag` → `apply_action` del widget). CONFIRM no se auto-confirma (requiere el sí del
operador); se reporta como pendiente. (V2-086: enviar al cluster ya NO pasa por aquí — es la tool
`cluster_send`, no una data-op de widget.)
"""
from __future__ import annotations


async def execute(tool_calls: list) -> dict:
    """Despacha la data-op del turno y devuelve el parte, o dice que la saltó y POR QUÉ."""
    wd = next((t["args"] for t in (tool_calls or []) if t.get("name") == "widget_data"), {}) or {}
    wid = str(wd.get("widget_id") or "").strip().lower()
    act = str(wd.get("action") or "").strip()
    pl = wd.get("payload") if isinstance(wd.get("payload"), dict) else {}
    from nucleo.flash import frontend as _fe
    from widgets import actions as _wa
    mode = _fe.action_mode(wid, act)
    if mode != _wa.FAST:
        return {"executed": "widget_data_skipped", "mode": str(mode), "widget": wid, "act": act}
    import widgets as _w
    await _w.dispatch_tag("widget.data", {"id": wid, "data": {"action": act, "payload": pl}})
    return {"executed": "widget_data", "widget": wid, "act": act}
