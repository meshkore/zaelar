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
from widgets import paths as _paths

HERE = _paths.BUILTIN_ROOT

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


# PUBLIC facade for other domains (nucleo/worker_api, Susurro...): run a widget hook with the SAME isolation (bounded
# pool + timeout) without importing private functions from this module.
MISSING = _MISSING


async def run_widget_hook(wid: str, fn: str, caller):
    return await _run_widget(wid, fn, caller)


# COMPACT index fields (V2-085). The minimum needed to RESOLVE and IDENTIFY a widget without downloading its manifest:
# who it is (id/name/title), what it is for (whenToUse, clipped), how it is called (aliases), where it comes from
# (origin), and whether it is ephemeral (transient — frontend routes activity cards through that). NO `actions`,
# payload schemas, `usage`, `refs`, or prose: that is on-demand load through /widgets/{id}/manifest.
# `size`/`fullscreen` enter here (2026-08-12) because the CANVAS consumes them when mounting the card, before anyone
# requests the full manifest: preferred size for a fluid-width surface and whether "fullscreen" means native (video)
# or maximize inside the app. These are two tiny fields; requesting the whole manifest to read them would bring back
# the O(N·manifest) that V2-085 removed.
_INDEX_FIELDS = ("id", "title", "name", "transient", "kind", "icon", "size", "fullscreen", "live_title")
_INDEX_PURPOSE_MAX = 120


def _index_row(w: dict) -> dict:
    """One compact-index row from a full manifest."""
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
    """COMPACT catalog INDEX (V2-085) — by default, NOT full manifests.

    Measured 2026-08-01: with 16 widgets this endpoint returned 25,639 chars of full manifests, and its only real
    consumer (`frontend/app/widgets/desktop.js::_resolve`) only wanted **ids** and four header fields. O(N) over the
    WHOLE manifest: with thousands of widgets, each canvas startup downloaded megabytes to resolve one id. The index
    carries only identity + clipped purpose (~10× less), and the full manifest is requested per widget when truly
    needed: `GET /widgets/{id}/manifest`.

    `?full=1` = explicit ADMINISTRATIVE escape hatch (debugging, export, tools). Never the default path: if something
    needs it hot, it is missing an on-demand load.

    `?q=` + `?limit=` bound the index server-side (same name/alias ranking as the voice resolver). The index remains
    O(N) by nature — it is the inventory — so a consumer that cannot handle thousands of rows must paginate/search
    here instead of downloading everything. `count` is ALWAYS the real catalog total, not the returned row count: no
    one should confuse an excerpt with the inventory."""
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
    """UNIFIED name + alias registry (V2-082): user widgets (catalog, editable aliases) + system surfaces (fixed
    aliases). Each entry {id, name, aliases, surface}. Consumed by the frontend header (name button + alias dropdown).
    Also refreshes the visibility projection in state."""
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
    """Tell the frontend (SSE) that a widget's aliases changed → the header refreshes its dropdown live.
    Best-effort (notification failure does not break the write, which is already on disk)."""
    try:
        from voice.observer import emit
        emit("widget", "alias", extra={"id": wid, "aliases": res.get("aliases") or []})
    except Exception:
        pass


@router.post("/widgets/{wid}/aliases")
async def add_alias(wid: str, payload: dict):
    """Add an alias to the widget (V2-082) — from the canvas header (text) or voice flow. Surgical manifest write with
    collision guard (one alias = one piece). 409 if another piece already uses it."""
    from . import aliases
    res = aliases.add(_safe(wid), str((payload or {}).get("alias") or ""))
    if res.get("ok"):
        _emit_alias_change(_safe(wid), res)
        return JSONResponse(res)
    code = 409 if res.get("owner") else 404 if "no existe" in str(res.get("error")) else 400
    return JSONResponse(res, status_code=code)


@router.delete("/widgets/{wid}/aliases/{alias}")
async def remove_alias(wid: str, alias: str):
    """Remove a widget alias (V2-082). Does not allow removing the canonical NAME (without a name it cannot open)."""
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
    p = os.path.join(_paths.dir_for(_safe(wid)) or _paths.new_dir(_safe(wid)), "widget.js")
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


async def dispatch_raw(wid: str, action: str, payload: dict):
    """The RAW widget mutation: route to its owner if `backed`, or call its `apply_action` off-loop. WITHOUT the
    run-state gate or channel exclusivity (see `_dispatch`).

    Exists separately because STOP needs this path: if suspending a widget went through the same gate that gates
    actions, stopping while the agent is already stopped would reject itself. Only legitimate shortcut user:
    `widgets/producers.py`. Everything external (UI, brain, cron) enters through `_dispatch`."""
    wid = _safe(wid)
    routed = _route_backed(wid, action, payload or {})      # backed widget → owner's mailbox
    if routed is not None:
        return routed
    return await _run_widget(wid, "apply_action", lambda fn: fn(action, payload or {}))


async def _dispatch(wid: str, action: str, payload: dict):
    """SINGLE FUNNEL for every widget mutation coming from outside (V2-092). Three steps, in this order:

    1. **Gate**: with the agent STOPPED, an action that would make the widget produce is rejected (not half-applied
       and undone later: that would leave weird traces in its store and, for something like `load`, would already have
       done network work).
    2. **The action**, through the usual path.
    3. **Exclusivity**: if it just took an exclusive channel (the speaker), silence the others on that channel. After
       applying it, because who occupies the channel is read from REAL state, not intent.

    Steps 1 and 3 are best-effort: production-policy failure cannot crash a normal data-op."""
    try:
        from . import producers
        denied = producers.gate(wid, action)
        if denied is not None:
            return denied
    except Exception:
        pass
    res = await dispatch_raw(wid, action, payload)
    try:
        from . import producers
        await producers.enforce_exclusive(wid, action)
    except Exception:
        pass
    return res


@router.post("/widgets/{wid}/action")
async def widget_action(wid: str, payload: dict):
    wid = _safe(wid)
    action, data = payload.get("action", ""), payload.get("payload") or {}
    # V2-039: this route is triggered by the UI (operator presses a card button) → note provenance so the resulting
    # widget/data event (store.save) is attributed to "user". Also emit the action ACT.
    try:
        from widgets import provenance as _prov
        from voice.observer import emit as _emit
        _prov.note(wid, "user")
        _emit("widget", "action", extra={"id": wid, "action": str(action), "src": "user"})
    except Exception:
        pass
    res = await _dispatch(wid, action, data)
    if res is _MISSING:
        return JSONResponse({"error": "no data module"}, status_code=404)
    return JSONResponse(res)


async def brain_action(wid: str, action: str, payload: dict) -> dict:
    """SAME mutation path as POST /widgets/{id}/action (off-loop, bounded pool, hard timeout) — the in-process
    call used by the brain-side [[widget.data:ID]] tag (widgets/__init__.py:dispatch_tag), so Hermes can change
    a widget's OWN stored data with the exact contract its UI buttons already use. No HTTP round-trip: same
    process, same isolation guarantees. Never raises — degrades to {"error": …}.

    V2-390 — NAMES THE ACTION, like the UI route above already did. The operator's own clicks emitted
    `widget/action` with the action in it; the BRAIN's ops emitted only the anonymous `widget/data` that
    `store.save` fires, so from outside every brain-driven op looked the same. Measured on
    `play-music-and-build-playlist` (2026-08-27 13:29): the music was really playing (`yt.videoId` set,
    `paused: false`) and the list «Curro» really existed, and the round scored **1/5 for "alucinación de
    éxito"** — the judge wrote that the mechanism proves neither happened, citing "solo operaciones genéricas
    de datos". It could not tell `add_to_playlist` from `set_volume`, so it read the ops as nothing.

    An op that FAILED gets its own event instead of being folded into the same line: a refusal the widget
    reported (`nothing_playing`) and a change that went through are opposite facts, and collapsing them is how
    «Hecho.» keeps surviving. Same reading as V2-346 — a datum that names them all names none of them.
    """
    wid = _safe(wid)
    try:
        from voice.observer import emit as _emit
        from widgets import provenance as _prov
        _emit("widget", "action", extra={"id": wid, "action": str(action), "src": _prov.who(wid)})
    except Exception:
        pass
    res = await _dispatch(wid, action, payload or {})
    res = {"error": "no data module"} if res is _MISSING else res
    try:
        if isinstance(res, dict) and (res.get("error") or res.get("ok") is False):
            from voice.observer import emit as _emit2
            # `is_error` va DENTRO de `extra`: `emit` no lo acepta como kwarg y los extras se aplanan al
            # evento. Con el kwarg suelto salta un TypeError que este mismo `except` se traga, así que el
            # evento de fallo no se emitiría NUNCA y nadie se enteraría — el defecto que estoy cerrando,
            # cometido al cerrarlo.
            _emit2("widget", "action_failed", text=str(res.get("message") or res.get("error") or "")[:160],
                   extra={"id": wid, "action": str(action), "error": str(res.get("error") or ""),
                          "is_error": True})
    except Exception:
        pass
    return res


@router.delete("/widgets/{wid}")
async def delete_widget(wid: str):
    """Widget deletion — DELEGATES to `widgets/lifecycle.delete_widget`: removes folder + private store, invalidates
    the catalog, closes the card (SSE), and writes the TOMBSTONE to memory (history preserved — "you deleted it on
    <date>"). One deletion path in all zaelar. Catalog/brief stop knowing the id immediately."""
    from . import lifecycle
    res = await lifecycle.delete_widget(_safe(wid), "user")   # V2-039: deletion triggered by operator UI
    if not res.get("ok"):
        code = 404 if res.get("error") == "widget no encontrado" else 500
        return JSONResponse(res, status_code=code)
    return JSONResponse(res)


@router.post("/widgets/{wid}/confirm")
async def confirm_widget(wid: str, payload: dict):
    """Resolve pending CONFIRMATION for an irreversible widget action, triggered by the card's Yes/No button.
    `{ok: bool}`. With `ok` → execute; without `ok` → cancel and remove the overlay. Two classes, and BOTH have
    to execute here (`widgets/confirm.py`): `delete` (the whole widget) and `data` (an irreversible data-op
    declared `confirm:true` in the manifest, V2-025).

    ⚠️ **`data` no se ejecutaba desde el BOTÓN, y era peor que no hacer nada** (encontrado en la sesión
    319252e7, 2026-08-15). Este endpoint solo sabía de `delete`; con una data-op devolvía `400 acción no
    soportada: data` — pero `confirm.resolve()` ya había CONSUMIDO la confirmación pendiente. O sea que pulsar
    «Sí» destruía la mutación guardada y no ejecutaba nada: la única salida era volver a pedirlo, que abría otra
    confirmación, y así en bucle. El operador dijo «Lo he confirmado yo con el botón» y la agenda seguía llena;
    el Susurro lo diagnosticó bien («el sistema no ejecutó la acción real tras la confirmación, repitiendo la
    pregunta sin avanzar») y escaló a un worker, que chocó con el MISMO gate.

    La mitad por VOZ sí estaba completa (`providers/nucleo.py::_resolve_confirm`), y esa asimetría es lo que
    hizo el fallo difícil de ver: la misma acción funcionaba diciendo «sí» y no funcionaba pulsando «Sí».
    """
    from . import confirm, lifecycle
    wid = _safe(wid)
    ok = bool((payload or {}).get("ok"))
    p = confirm.resolve(wid, ok)
    if p is None:
        return JSONResponse({"ok": False, "error": "no hay confirmación pendiente"}, status_code=409)
    if not ok:
        return JSONResponse({"ok": True, "cancelled": True, "id": p["widget_id"]})
    if p.get("action") == "delete":
        res = await lifecycle.delete_widget(p["widget_id"], "user")   # V2-039: confirmed by operator Yes/No button
        return JSONResponse(res, status_code=200 if res.get("ok") else 500)
    if p.get("action") == "data" and isinstance(p.get("op"), dict):
        op = p["op"]
        name = str(op.get("action") or "").strip()
        if not name:
            return JSONResponse({"ok": False, "error": "confirmación sin acción guardada"}, status_code=400)
        # Mismo despacho que la rama de voz: la mutación va por `apply_action` del propio widget, JAMÁS a código.
        res = await brain_action(p["widget_id"], name, op.get("payload") or {})
        _emit_confirmed(p["widget_id"], name)
        return JSONResponse({"ok": not (isinstance(res, dict) and res.get("error")),
                             "id": p["widget_id"], "action": name, "result": res})
    return JSONResponse({"ok": False, "error": f"acción no soportada: {p.get('action')}"}, status_code=400)


def _emit_confirmed(wid: str, action: str) -> None:
    """El operador tiene que VER que su «Sí» ejecutó algo. Sin esta traza, el bucle de arriba era invisible en el
    visor: se veía la confirmación pedida una y otra vez y nunca una ejecución ([[feedback_visible_state_over_silent_state]])."""
    try:
        from voice.observer import emit
        emit("brain", "✅ acción irreversible confirmada (botón)", role="system", text=f"{wid}:{action}")
    except Exception:
        pass


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
                # V2-039: audit CREATE/MODIFY widget code. Intentionally NON-canonical label (does not collide with
                # the frontend create/modify handler, which expects spec/change); op + src make it filterable.
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
    """Modify an EXISTING widget with the atomic agent (e.g. 'add a column with price and seller')."""
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
