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
    """Despacha las data-ops del turno y devuelve el parte, o dice cuál saltó y POR QUÉ.

    V2-391 — VARIAS, no una. Cuáles entran lo decide `data_ops.admite_data_op`, compartido con la voz
    para que no pueda divergir: mismo widget y misma acción con payloads DISTINTOS sí (dos enlaces pegados),
    duplicado exacto no (la cita doble), acción distinta sobre el mismo widget tampoco (la enumeración).
    """
    from nucleo.flash import frontend as _fe
    from nucleo.flash import data_ops as _rg
    from widgets import actions as _wa

    todas = [t.get("args") or {} for t in (tool_calls or []) if t.get("name") == "widget_data"]
    admitidas: list[dict] = []
    for a in todas:
        if _rg.admite_data_op(a, admitidas):
            admitidas.append(a)
    if not admitidas:
        return {"executed": "widget_data_skipped", "mode": "sin data-op utilizable", "widget": "", "act": ""}

    import widgets as _w
    hechas, saltadas = [], []
    for a in admitidas:
        wid = str(a.get("widget_id") or "").strip().lower()
        act = str(a.get("action") or "").strip()
        pl = a.get("payload") if isinstance(a.get("payload"), dict) else {}
        mode = _fe.action_mode(wid, act)
        if mode != _wa.FAST:
            saltadas.append({"widget": wid, "act": act, "mode": str(mode)})
            continue
        await _w.dispatch_tag("widget.data", {"id": wid, "data": {"action": act, "payload": pl}})
        hechas.append({"widget": wid, "act": act})
    if not hechas:
        s0 = saltadas[0]
        return {"executed": "widget_data_skipped", "mode": s0["mode"], "widget": s0["widget"], "act": s0["act"]}
    # `widget`/`act` singulares se conservan: son la forma que ya leen el informe y los guardas de antes, y
    # cambiarla por una lista rompería la lectura sin avisar. Lo nuevo va al lado.
    parte = {"executed": "widget_data", "widget": hechas[0]["widget"], "act": hechas[0]["act"],
             "ops": hechas}
    # Lo que NO se hizo se DICE, en vez de dejar el parte contando solo lo que salió bien.
    if len(todas) > len(hechas):
        parte["descartadas"] = len(todas) - len(hechas)
    if saltadas:
        parte["sin_permiso"] = saltadas
    return parte
