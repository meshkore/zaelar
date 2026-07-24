"""widgets/navegador/act_api.py — PUENTE DE NAVEGADOR para agentes Claude Code (V2-036 F3).

Expone las primitivas del `TaskBrowser` del owner como una API request/response SÍNCRONA para que un agente Claude
Code headless DIRIJA el Chromium de zaelar paso a paso (navigate/click/type/scroll/snapshot/extract) con su propia
inteligencia — sustituye al bucle barato DOM→visión (Haiku). Corre en el loop de uvicorn, el MISMO que el owner del
navegador (backed), así que puede llamar a los métodos del `TaskBrowser` directamente (no por el mailbox
fire-and-forget). Lo invoca el CLI `nucleo/nav_cli.py` (`hbweb`). Local/loopback: mismo modelo de confianza que el
resto de la API.
"""
from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

router = APIRouter()


def _shot_path(task_id: str) -> str:
    """Ruta ABSOLUTA del PNG de la viewport de esta pestaña (lo escribe TaskBrowser._capture tras cada acción) →
    el worker la LEE con Read. Best-effort: si algo falla devuelve '' (el worker sigue con el snapshot de texto)."""
    try:
        import os
        from widgets import store
        from widgets.navegador import owner
        return os.path.abspath(f"{store.data_dir(owner.WID)}/shot-{task_id}.png")
    except Exception:
        return ""


def _emit_nav(nav_tid: str, label: str, text: str) -> None:
    """V2-048: fila de observabilidad del RESULTADO de una acción de navegador — a qué PÁGINA llegó / qué ENCONTRÓ
    (lo que el comando NO dice, solo lo sabe el browser). Label distinto del `step` de intención → sin colisión con
    el flood-dedup de `navegador`. Sella trace/span del worker dueño de la pestaña. Best-effort, nunca lanza."""
    try:
        from voice.observer import emit
        from nucleo import dispatch
        extra = {"id": nav_tid}
        r = dispatch.record_by_nav_task(nav_tid)
        if r is not None and getattr(r, "trace_id", ""):
            extra["trace"] = r.trace_id
            extra["span"] = f"worker:{r.task_id}"
        emit("navegador", label, text=text[:200], extra=extra)
    except Exception:
        pass


@router.post("/api/navegador/act")
async def navegador_act(task_id: str = Body(..., embed=True), action: str = Body(..., embed=True),
                        args: dict = Body(default_factory=dict, embed=True)):
    """Ejecuta UNA acción de navegador en la pestaña de `task_id` y devuelve el ESTADO resultante para que el agente
    razone el siguiente paso. Acciones: snapshot | navigate{url} | click{ref} | type{ref,text,submit} | scroll{dy} |
    press{key} | extract{limit}. `click`/`type` usan las refs del ÚLTIMO snapshot → pide snapshot antes de actuar.
    El confirm-gate de acciones irreversibles del owner sigue aplicando. Best-effort: nunca lanza."""
    action = (action or "").strip()
    args = args or {}
    try:
        from widgets.navegador import owner
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": f"navegador no disponible: {e}"}, status_code=503)
    try:
        tb = owner._task_browsers.get(task_id)
        if tb is None:
            tb = owner.TaskBrowser(task_id)
            owner._task_browsers[task_id] = tb
        await tb.ensure()

        if action == "snapshot":
            snap = await tb.snapshot_for_agent()
            return {"ok": True, "shot": _shot_path(task_id), **snap}
        if action == "look":
            # V2-049 VISIÓN: captura FRESCA del viewport a disco → el worker la LEE con su tool Read (ve la página
            # como un humano) y actúa por coordenadas (click_at/type_at). Es el camino robusto para formularios/
            # date-pickers/selects que el snapshot de texto no basta a describir.
            await tb._capture()
            snap = {}
            try:
                snap = await tb.snapshot_for_agent()
            except Exception:
                pass
            _emit_nav(task_id, "🧭 vista", f"captura {snap.get('title') or snap.get('url') or ''}"[:200])
            return {"ok": True, "shot": _shot_path(task_id), "viewport": {"width": 1280, "height": 800}, **snap}
        if action == "extract":
            items = await tb.extract_listings(int(args.get("limit", 14)))
            _emit_nav(task_id, "🧭 resultados", f"{len(items)} anuncios/resultados en la página")
            return {"ok": True, "listings": items, "n": len(items)}
        if action in ("navigate", "click", "type", "select_option", "scroll", "press", "click_at", "type_at"):
            ok, msg = await tb.agent_act(action, args)
            # devuelve el estado FRESCO tras la acción → el agente ve el resultado y decide el siguiente paso.
            snap = {}
            try:
                snap = await tb.snapshot_for_agent()
            except Exception:
                pass
            # observabilidad: a qué PÁGINA llevó la acción (título · url) — solo el browser lo sabe (V2-048).
            page = " · ".join(x for x in (str(snap.get("title") or "").strip(),
                                          str(snap.get("url") or "").strip()) if x)
            if page:
                _emit_nav(task_id, "🧭 página", page)
            # la ruta del PNG FRESCO (cada acción llama a _capture) → el worker puede Read la vista tras actuar.
            return {"ok": bool(ok), "msg": msg, "shot": _shot_path(task_id), **snap}
        return JSONResponse({"ok": False, "error": f"acción desconocida: {action}"}, status_code=400)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": f"{type(e).__name__}: {str(e).splitlines()[0][:160]}"},
                            status_code=500)
