#
# Widgets HTTP API — an ISOLATED router mounted in the zaelar app. Nothing here touches the voice pipeline.
# Endpoints are catalog-driven so adding a widget = drop a folder with manifest.json + widget.js + a data module.
#
import asyncio
import importlib
import os
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse

from . import runtime

router = APIRouter()
HERE = os.path.dirname(os.path.abspath(__file__))

# Widget python (data.py) NEVER runs on the server event loop: the voice pipeline shares that loop, so a slow
# fetch or an infinite loop inside a widget would mute zaelar entirely. Every hook runs in this DEDICATED bounded
# pool (separate from the default executor used by /generate) under a hard timeout; on timeout or crash the widget
# degrades to {"error": …} and the rest of the system keeps working — "a widget must never break the system".
# A hung call still burns one pool thread until it returns (threads can't be killed), but the pool is bounded, so
# the worst case is a degraded widget layer, never a blocked voice loop.
_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="widget-data")
_TIMEOUT = float(os.environ.get("WIDGETS_DATA_TIMEOUT", "8"))   # widget contract caps fetches at 6s → headroom
_MISSING = object()                                             # sentinel: widget has no data module / no such hook
_PROGRESS_SECS = float(os.environ.get("WIDGETS_PROGRESS_SECS", "30"))   # cadence of generation still-alive notes


def _safe(wid: str) -> str:
    """Normalize a widget id at the trust boundary: only [A-Za-z0-9_-], no dots/paths (blocks import/path tricks)."""
    return "".join(c for c in os.path.basename(wid or "") if c.isalnum() or c in "-_")


def _data_module(widget_id: str):
    """Lazy-import the widget's python data module (widgets/<id>/data.py), if it has one."""
    wid = _safe(widget_id)
    if not wid:
        return None
    try:
        return importlib.import_module(f"widgets.{wid}.data")
    except Exception:
        return None


def _call_widget(wid: str, fn: str, caller):
    """Resolve + invoke a widget hook. Runs INSIDE the worker thread — importing data.py executes its top-level
    code, which can be just as slow/broken as the hook itself, so resolution must stay off the loop too."""
    mod = _data_module(wid)
    target = getattr(mod, fn, None) if mod else None
    if not callable(target):
        return _MISSING
    return caller(target)


async def _run_widget(wid: str, fn: str, caller):
    """Run a widget hook off the event loop with a hard timeout. Returns _MISSING (no module/hook) or the hook's
    result; a timeout or crash becomes a degraded {"error": …} instead of stalling or 500-ing the server."""
    fut = asyncio.get_running_loop().run_in_executor(_POOL, lambda: _call_widget(wid, fn, caller))
    try:
        return await asyncio.wait_for(fut, timeout=_TIMEOUT)
    except asyncio.TimeoutError:
        return {"error": f"widget '{wid}' timed out after {_TIMEOUT:.0f}s"}
    except Exception as e:
        return {"error": f"widget '{wid}' failed: {type(e).__name__}: {e}"}


# Fachada PÚBLICA para otros dominios (nucleo/worker_api, Susurro…): correr un hook de un widget con el MISMO
# aislamiento (pool acotado + timeout) sin importar privados de este módulo.
MISSING = _MISSING


async def run_widget_hook(wid: str, fn: str, caller):
    return await _run_widget(wid, fn, caller)


# Campos del ÍNDICE compacto (V2-085). Lo mínimo para RESOLVER e IDENTIFICAR un widget sin descargar su manifest:
# quién es (id/name/title), para qué (whenToUse, recortado), cómo se le llama (aliases), de dónde viene (origin) y
# si es efímero (transient — el frontend rutea las tarjetas de actividad por ahí). NADA de `actions`, payload
# schemas, `usage`, `refs` ni prosa: eso es carga bajo demanda vía /widgets/{id}/manifest.
_INDEX_FIELDS = ("id", "title", "name", "transient", "kind", "icon")
_INDEX_PURPOSE_MAX = 120


def _index_row(w: dict) -> dict:
    """Una fila del índice compacto a partir de un manifest completo."""
    from . import registry as _registry
    row = {k: w[k] for k in _INDEX_FIELDS if k in w}
    row["id"] = str(w.get("id") or "")
    purpose = str(w.get("whenToUse") or w.get("title") or "").strip().replace("\n", " ")
    if purpose:
        row["whenToUse"] = purpose[:_INDEX_PURPOSE_MAX]
    ident = _registry.widget_identity(w)
    row["name"], row["aliases"], row["origin"] = ident["name"], ident["aliases"], ident["origin"]
    return row


@router.get("/widgets")
async def list_widgets(full: int = 0, q: str = "", limit: int = 0):
    """ÍNDICE COMPACTO del catálogo (V2-085) — por defecto, NO los manifests completos.

    Medido 2026-08-01: con 16 widgets este endpoint devolvía 25.639 chars de manifests íntegros y su único
    consumidor real (`frontend/app/widgets/desktop.js::_resolve`) solo quería los **ids** y cuatro campos de
    cabecera. O(N) sobre el manifest ENTERO: con miles de widgets, cada arranque del canvas se descargaba megas
    para resolver un id. El índice lleva solo identidad + propósito recortado (~10× menos) y el manifest completo
    se pide por widget cuando de verdad hace falta: `GET /widgets/{id}/manifest`.

    `?full=1` = escotilla ADMINISTRATIVA explícita (depuración, export, herramientas). Nunca es el camino por
    defecto: si algo la necesita en caliente, es que le falta una carga bajo demanda.

    `?q=` + `?limit=` acotan el índice server-side (mismo ranking por nombre/alias que el resolver de voz). El
    índice sigue siendo O(N) por naturaleza — es el inventario —, así que un consumidor que no pueda con miles de
    filas debe paginar/buscar por aquí en vez de descargarlo entero. `count` es SIEMPRE el total real del
    catálogo, no el número de filas devueltas: nadie debe confundir un extracto con el inventario."""
    cat = runtime.catalog()
    total = len(cat)
    if full:
        return JSONResponse({"widgets": cat, "count": total, "returned": total, "full": True})
    if q:
        ranked_ids = [str(w.get("id") or "") for _s, w in runtime.rank(q, limit=max(1, limit or 20))]
        order = {wid: i for i, wid in enumerate(ranked_ids)}
        cat = sorted((w for w in cat if str(w.get("id") or "") in order),
                     key=lambda w: order[str(w.get("id") or "")])
    if limit and limit > 0:
        cat = cat[:limit]
    rows = [_index_row(w) for w in cat]
    return JSONResponse({"widgets": rows, "count": total, "returned": len(rows), "full": False})


@router.get("/widgets/identify")
async def identify(q: str = ""):
    """Map a voice/text request to a widget (with disambiguation candidates)."""
    return JSONResponse(runtime.identify(q))


@router.get("/widgets/registry")
async def registry_endpoint():
    """Registro UNIFICADO de nombres + alias (V2-082): widgets de usuario (catálogo, alias editables) + superficies
    de sistema (alias fijos). Cada entrada {id, name, aliases, surface}. Lo consume el header del frontend (botón-
    nombre + desplegable de alias). De paso refresca la proyección de visibilidad en el estado."""
    from . import registry as _registry
    rows = _registry.registry()
    try:
        _registry.refresh_state()
    except Exception:
        pass
    return JSONResponse({"registry": rows})


@router.get("/widgets/{wid}/manifest")
async def manifest(wid: str):
    w = runtime.get(_safe(wid))
    return JSONResponse(w or {"error": "unknown widget"}, status_code=200 if w else 404)


def _emit_alias_change(wid: str, res: dict) -> None:
    """Avisa al frontend (SSE) de que cambiaron los alias de un widget → el header refresca su desplegable en vivo.
    Best-effort (un fallo de notificación no rompe la escritura, que ya está hecha en disco)."""
    try:
        from voice.observer import emit
        emit("widget", "alias", extra={"id": wid, "aliases": res.get("aliases") or []})
    except Exception:
        pass


@router.post("/widgets/{wid}/aliases")
async def add_alias(wid: str, payload: dict):
    """Añade un alias al widget (V2-082) — desde el header del canvas (texto) o el flujo de voz. Escritura
    quirúrgica del manifest con guard de colisión (un alias = una sola pieza). 409 si ya lo usa otra pieza."""
    from . import aliases
    res = aliases.add(_safe(wid), str((payload or {}).get("alias") or ""))
    if res.get("ok"):
        _emit_alias_change(_safe(wid), res)
        return JSONResponse(res)
    code = 409 if res.get("owner") else 404 if "no existe" in str(res.get("error")) else 400
    return JSONResponse(res, status_code=code)


@router.delete("/widgets/{wid}/aliases/{alias}")
async def remove_alias(wid: str, alias: str):
    """Quita un alias del widget (V2-082). No permite quitar el NOMBRE canónico (sin nombre no se abre)."""
    from . import aliases
    res = aliases.remove(_safe(wid), alias)
    if res.get("ok"):
        _emit_alias_change(_safe(wid), res)
        return JSONResponse(res)
    code = 404 if "no existe" in str(res.get("error")) else 400
    return JSONResponse(res, status_code=code)


@router.get("/widgets/{wid}/widget.js")
async def widget_js(wid: str):
    """Serve the widget's client render module (lazy-loaded by the canvas host). `no-cache` forces revalidation
    on every load (same fix as server/__init__.py's StaticFiles for frontend/) — without it, the browser's ES
    module + HTTP cache can keep serving an OLD widget.js (stale styles/behavior) after an edit, indefinitely,
    since desktop.js's dynamic import() has no cache-busting query param on the initial load."""
    p = os.path.join(HERE, _safe(wid), "widget.js")
    if not os.path.isfile(p):
        return JSONResponse({"error": "no widget.js"}, status_code=404)
    return FileResponse(p, media_type="text/javascript", headers={"Cache-Control": "no-cache"})


@router.get("/widgets/{wid}/asset/{name}")
async def widget_asset(wid: str, name: str):
    """Serve a binary asset from a widget's OWN data directory (widgets/_data/<id>/) — screenshots, cover art,
    whatever a widget-app renders that isn't JSON. Added for the navegador (its live page screenshot). Path-safe
    on both ids (only the basename, [A-Za-z0-9._-]); `no-cache` so a fresh frame with the same filename never
    serves stale (the widget cache-busts with ?v=<rev> anyway). Never a way out of the widget's namespace."""
    from . import store
    safe_name = "".join(c for c in os.path.basename(name or "") if c.isalnum() or c in "._-")
    p = os.path.join(store.data_dir(_safe(wid)), safe_name)
    if not safe_name or not os.path.isfile(p):
        return JSONResponse({"error": "no such asset"}, status_code=404)
    return FileResponse(p, headers={"Cache-Control": "no-cache"})


@router.get("/widgets/{wid}/data")
async def widget_data(wid: str, q: str = ""):
    def call(view_data):
        try:
            return view_data(q=q)
        except TypeError:                                   # older widgets take no query argument
            return view_data()
    res = await _run_widget(wid, "view_data", call)
    if res is _MISSING:
        return JSONResponse({"error": "no data module"}, status_code=404)
    return JSONResponse(res)


def _route_backed(wid: str, action: str, payload: dict):
    """A "backed" widget (kind:"backed") owns a live backend process (e.g. the navegador's headless Chromium).
    Its data.py is READ-ONLY: a mutation is not applied inline, it's ENQUEUED into the owner's mailbox, which the
    supervisor drains in order (zaelar-modules.md §Widget-apps — one writer by construction, no two-writer race).
    Returns a queued-ack dict if it was enqueued, or None to fall back to the normal off-loop apply_action path
    (widget is passive, or its owner isn't running / got disabled)."""
    try:
        from . import supervisor
        if supervisor.is_backed(wid) and supervisor.enqueue(wid, action, payload or {}):
            return {"ok": True, "queued": True, "id": wid}
    except Exception:
        pass
    return None


@router.post("/widgets/{wid}/action")
async def widget_action(wid: str, payload: dict):
    wid = _safe(wid)
    action, data = payload.get("action", ""), payload.get("payload") or {}
    # V2-039: esta ruta la dispara la UI (el operador pulsa un botón de la tarjeta) → anota la procedencia para que
    # el evento widget/data resultante (store.save) quede atribuido a "user". Emite además el ACTO de la acción.
    try:
        from widgets import provenance as _prov
        from voice.observer import emit as _emit
        _prov.note(wid, "user")
        _emit("widget", "action", extra={"id": wid, "action": str(action), "src": "user"})
    except Exception:
        pass
    routed = _route_backed(wid, action, data)               # backed → owner mailbox (owner writes + emits SSE)
    if routed is not None:
        return JSONResponse(routed)
    res = await _run_widget(wid, "apply_action", lambda fn: fn(action, data))
    if res is _MISSING:
        return JSONResponse({"error": "no data module"}, status_code=404)
    return JSONResponse(res)


async def brain_action(wid: str, action: str, payload: dict) -> dict:
    """SAME mutation path as POST /widgets/{id}/action (off-loop, bounded pool, hard timeout) — the in-process
    call used by the brain-side [[widget.data:ID]] tag (widgets/__init__.py:dispatch_tag), so Hermes can change
    a widget's OWN stored data with the exact contract its UI buttons already use. No HTTP round-trip: same
    process, same isolation guarantees. Never raises — degrades to {"error": …}."""
    wid = _safe(wid)
    routed = _route_backed(wid, action, payload or {})      # backed widget → same mailbox path as the UI/POST
    if routed is not None:
        return routed
    res = await _run_widget(wid, "apply_action", lambda fn: fn(action, payload or {}))
    return {"error": "no data module"} if res is _MISSING else res


@router.delete("/widgets/{wid}")
async def delete_widget(wid: str):
    """Borrado del widget — DELEGA en `widgets/lifecycle.delete_widget`: quita carpeta + store privado, invalida
    el catálogo, cierra la tarjeta (SSE) y escribe la LÁPIDA en memoria (histórico conservado — "lo borraste el
    <fecha>"). Un solo camino de borrado en todo zaelar. El catálogo/brief dejan de conocer el id al instante."""
    from . import lifecycle
    res = await lifecycle.delete_widget(_safe(wid), "user")   # V2-039: borrado disparado por la UI del operador
    if not res.get("ok"):
        code = 404 if res.get("error") == "widget no encontrado" else 500
        return JSONResponse(res, status_code=code)
    return JSONResponse(res)


@router.post("/widgets/{wid}/confirm")
async def confirm_widget(wid: str, payload: dict):
    """Resuelve la CONFIRMACIÓN pendiente de una acción irreversible del widget (hoy: borrar), disparada por el
    botón «Sí/No» de la tarjeta. `{ok: bool}`. Con `ok` → ejecuta el borrado determinista (memoria incluida); sin
    `ok` → cancela y quita el overlay. Mismo camino que el "sí/no" por voz (ver `widgets/confirm.py`)."""
    from . import confirm, lifecycle
    wid = _safe(wid)
    ok = bool((payload or {}).get("ok"))
    p = confirm.resolve(wid, ok)
    if p is None:
        return JSONResponse({"ok": False, "error": "no hay confirmación pendiente"}, status_code=409)
    if not ok:
        return JSONResponse({"ok": True, "cancelled": True, "id": p["widget_id"]})
    if p.get("action") == "delete":
        res = await lifecycle.delete_widget(p["widget_id"], "user")   # V2-039: confirmado por botón Sí/No del operador
        return JSONResponse(res, status_code=200 if res.get("ok") else 500)
    return JSONResponse({"ok": False, "error": f"acción no soportada: {p.get('action')}"}, status_code=400)


@router.get("/widgets/{wid}/context")
async def widget_context(wid: str):
    """Coach 'memory seam' — text context the assistant injects to adopt the role over this widget."""
    res = await _run_widget(wid, "coach_context", lambda fn: fn())
    if res is _MISSING or isinstance(res, dict):            # dict = degraded {"error": …} → empty context
        return JSONResponse({"context": ""})
    return JSONResponse({"context": res})


async def _report_to_brain(kind: str, res: dict) -> None:
    """Close the fire-and-forget loop: generation is slow (~1-2 min) and the brain already moved on. Tell it the
    REAL outcome so it stops claiming "hecho" blind and never references a widget id that didn't get built.
      • success → a SILENT one-shot note for the brain's next turn (the widget already popped onto the canvas).
      • failure → the note AND a spoken/UI alert, because the brain likely said "hecho" and that was wrong.
    Best-effort — a feedback hiccup must never break the (already-completed) generation response."""
    wid = res.get("id") or "?"
    ok = bool(res.get("ok"))
    verb = "creó" if kind == "create" else "modificó"
    try:
        from voice import brain_notes
        if ok and res.get("existed"):
            return                                          # nothing built (already existed) → brain needs no note
        if ok:
            brain_notes.push(f"[SISTEMA] El widget '{wid}' se {verb} correctamente y ya está en el catálogo. "
                             f"Su id EXACTO es '{wid}'; para enseñarlo usa [[show:{wid}]]. No inventes otros ids.")
        else:
            err = str(res.get("error") or "error desconocido")
            brain_notes.push(f"[SISTEMA] FALLÓ {'crear' if kind == 'create' else 'modificar'} el widget '{wid}': "
                             f"{err}. El widget NO quedó listo — no afirmes que está hecho ni lo muestres; "
                             f"dile al operador que no se pudo y por qué.")
            try:
                from voice import proactive
                await proactive.notify("widget", f"No pude {'crear' if kind == 'create' else 'modificar'} "
                                       f"el widget «{wid}»: {err}.", kind="notify")
            except Exception:
                pass
    except Exception:
        pass


async def _run_generator(kind: str, wid_hint: str, call):
    """Run the slow generator (claude -p, ~1-2 min) off the loop, voicing periodic progress so the operator knows
    it's alive — the spinner alone reads as 'dead' after a minute. The first still-alive note (~30s) is spoken;
    later ones are UI-only (a toast every 30s, no nagging voice)."""
    import time

    fut = asyncio.ensure_future(asyncio.get_event_loop().run_in_executor(None, call))
    t0 = time.monotonic()
    spoken_once = False
    verb = "creando" if kind == "create" else "ajustando"
    while True:
        done, _ = await asyncio.wait({fut}, timeout=_PROGRESS_SECS)
        if done:
            gen_ms = round((time.monotonic() - t0) * 1000)
            try:
                from voice.observer import emit
                # V2-039: auditoría de CREAR/MODIFICAR código de widget. Label NO-canónico a propósito (no colisiona
                # con el handler create/modify del frontend, que espera spec/change); op + src lo hacen filtrable.
                emit("widget", f"🛠️ generator ({kind}): {wid_hint}",
                     extra={"id": wid_hint, "op": kind, "gen_ms": gen_ms, "src": "worker"})
            except Exception:
                pass
            return fut.result()
        secs = int(time.monotonic() - t0)
        try:
            from voice import proactive
            await proactive.notify("widget", f"Sigo {verb} el widget «{wid_hint}»… llevo ~{secs}s "
                                             f"(suele tardar 1-2 minutos).", speak=not spoken_once)
            spoken_once = True
        except Exception:
            pass


@router.post("/widgets/generate")
async def generate(payload: dict):
    """CREATE A NEW WIDGET ON DEMAND. The brain asks for a widget that doesn't exist yet; zaelar builds it with a
    headless Claude Code instance following the widget contract, validates it, and it auto-joins the catalog.
    Body: {id?, title?, spec}. Runs the (slow, blocking) generator off the event loop, with progress notices."""
    from .generator import generate_widget
    spec = str(payload.get("spec") or payload.get("prompt") or "").strip()
    wid = str(payload.get("id") or "")
    title = str(payload.get("title") or "")
    res = await _run_generator("create", wid or title or "nuevo", lambda: generate_widget(spec, wid, title))
    await _report_to_brain("create", res)
    return JSONResponse(res, status_code=200 if res.get("ok") else 422)


@router.post("/widgets/modify")
async def modify(payload: dict):
    """Modify an EXISTING widget with the atomic agent (e.g. 'añade una columna con precio y vendedor')."""
    from .generator import modify_widget
    wid = str(payload.get("id") or "")
    change = str(payload.get("change") or payload.get("spec") or "").strip()
    res = await _run_generator("modify", wid, lambda: modify_widget(wid, change))
    await _report_to_brain("modify", res)
    return JSONResponse(res, status_code=200 if res.get("ok") else 422)


async def resume_interrupted_generations() -> None:
    """Boot-time recovery (called from the server lifespan): a restart kills the headless agent mid-build and the
    old code lost the job entirely — the brain said 'lo estoy preparando' and nothing ever landed. The generator's
    journal (widgets/_data/_jobs.json) tells us what was in flight:
      • create → if the folder actually finished and validates, just tell the brain; otherwise discard the
        half-written folder and RELAUNCH (the operator asked for it and never got it).
      • modify → do NOT re-run blindly: the edit may be half-applied and its rollback backup died with the old
        process. Report it so the brain/operator can re-ask."""
    from . import generator
    from .generator import generate_widget

    for job in generator.take_pending_jobs():
        wid = str(job.get("id") or "")
        payload = job.get("payload") or {}
        if job.get("kind") == "create" and wid and payload.get("spec"):
            ok, _err = (await asyncio.get_event_loop().run_in_executor(None, generator._validate, wid)) \
                if generator.exists(wid) else (False, "not built")
            if ok:
                await _report_to_brain("create", {"ok": True, "id": wid})
                continue
            try:
                from voice import proactive
                await proactive.notify("widget", f"El servidor se reinició a mitad de crear el widget «{wid}»; "
                                                 f"lo relanzo ahora.", speak=False)
            except Exception:
                pass
            generator._discard(wid)                     # half-written folder → rebuild from clean
            res = await _run_generator("create", wid,
                                       lambda s=payload["spec"], w=wid, t=payload.get("title", ""):
                                       generate_widget(s, w, t))
            await _report_to_brain("create", res)
        elif wid:
            try:
                from voice import brain_notes
                brain_notes.push(f"[SISTEMA] El servidor se reinició mientras se modificaba el widget '{wid}': "
                                 f"el cambio pudo quedar a medias y NO se reaplicó. Si el operador aún lo quiere, "
                                 f"vuelve a emitir [[modify:{wid}]].")
            except Exception:
                pass
