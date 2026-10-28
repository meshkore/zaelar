"""The bridge's door: `POST /api/navegador/act` runs one action in a task's tab and returns the resulting state;
the phase each action announces in the Process tab, and the `extract` action.
Moved out of `act_api.py`; every module name is read through the package (`_f.<name>`), so a patch on `act_api`
still governs every call.
"""

import asyncio

from fastapi import Body
from fastapi.responses import JSONResponse
from nucleo.errors import brief as _brief
from nucleo.workers import progress as _progress
from widgets.navegador import lazy as _lazy
from widgets.results import door_verdict as _door

from widgets.navegador import act_api as _f


def _say_phase(nav_tid: str, phrase: str) -> None:
    """Set the OWNING session's phase from the browser side (V2-227 ámbito B1).

    «lanzo, tengo resultados» is a milestone the operator asked for by name, and it is the only one the browser
    knows and the worker's tool stream does not: the stream sees `extract` going out, not how much came back.
    Goes through `dispatch.session_phase`, the same door `hbnote` uses — B4 says the progress stream travels on
    the rail that exists, never on a parallel one.
    """
    try:
        from nucleo import dispatch as _d
        rec = _d.record_by_nav_task(str(nav_tid))
        if rec is not None and phrase:
            _d.session_phase(rec.task_id, phrase)
    except Exception:  # noqa: BLE001
        pass


def _phase_for_action(action: str, args: dict) -> str:
    """The PROCESS phrase for ONE browser action (V2-343). Empty means say nothing.

    Existe porque el operador no veía lo que ya medíamos. En la sesión `7575e81a` (2026-08-26, 21,6 min de
    encargo) el motor capturó **292 eventos de navegador, uno cada 4 segundos**, y a la pestaña de Proceso
    llegaron **8 líneas, una cada 162 s** — un factor 20 entre lo que sabemos y lo que enseñamos. Y no era el
    dedup comiéndose nada: las 8 que pasaban eran DISTINTAS y buenas. Era que nadie las mandaba.

    Las dos vías estaban tapadas por separado, y hay que arreglar la de aquí porque la otra no se puede:
      · `_say_phase` tenía UN solo llamante — `found()`, después de extraer. Las 36 navegaciones, los 27 clics
        y los 13 scrolls no lo llamaban nunca.
      · el stream del worker sí ve cada paso, pero el worker conduce el navegador por Bash, así que el paso
        llega como `where=sistema, action=ejecuta` → «ejecutando un paso», una CONSTANTE que el dedup de
        `sheets.record_phase` colapsa a una línea. Correctamente: tres líneas idénticas no son progreso.

    El vocabulario ya estaba escrito y es bueno (`nucleo/workers/progress.phrase`): lleva el HOST en
    `navigate`, así que «entrando en coches.net» y «entrando en milanuncios.com» son distintas y las dos pasan.
    Aquí no se inventa ninguna frase nueva — se le da al generador que ya existe el paso que ya conocíamos.

    El dedup NO se toca y es el contrapeso: sube la frecuencia de lo que INFORMA sin subir la del ruido.
    """
    act = (action or "").strip().lower()
    if not act:
        return ""
    tgt = ""
    key = _f._PHASE_TARGET.get(act)
    if key:
        tgt = str((args or {}).get(key) or "")
    try:
        return _progress.phrase({"where": "navegador", "action": act, "target": tgt}) or ""
    except Exception:  # noqa: BLE001
        return ""


async def _act_extract(tb, task_id: str, args: dict) -> dict:
    """`extract{limit}`: the listings of the page, looked at again when it was half-hydrated or had not painted its
    cards yet, counted by the ones with a name, and handed over to the sheet and the conversation."""
    _limit = int(args.get("limit", 14))
    items = await tb.extract_listings(_limit)
    # V2-294 — UNA PÁGINA A MEDIO CARGAR DEVUELVE FILAS HUECAS, Y ESO NO ES «SIN RESULTADOS».
    #
    # Medido en la tanda de las 13:57, `search-secondhand-monitor__es`: 3 s después de navegar al listado
    # con el filtro puesto, la extracción devolvió `{"title": "", "price": "0 €", "url": ".../item/…"}` —
    # las tarjetas ESQUELETO que un listado pinta mientras hidrata, con su enlace ya puesto y el resto en
    # blanco. El worker lo diagnosticó él solo («la extracción devuelve datos pobres, títulos vacíos y
    # precios en 0») y gastó dos vueltas en recuperarse; la siguiente extracción, sobre la misma página,
    # trajo monitores reales con precio. En la bici y la guitarra la ronda se acabó antes de recuperarse.
    #
    # Se mira UNA vez más porque la señal es inequívoca: hay filas, y NINGUNA tiene identidad. Con cero
    # filas no se reintenta —eso sí puede ser una página sin resultados, y hacerle esperar dos segundos a
    # cada búsqueda vacía es pagar por todas para arreglar unas pocas—; y un solo reintento, porque a la
    # segunda ya no es que esté cargando.
    if items and not _f.by_identity(items)[0]:
        await asyncio.sleep(_f._HYDRATE_WAIT_S)
        _retry = await tb.extract_listings(_limit)
        if _f.by_identity(_retry)[0]:
            _f._emit_nav(task_id, "🧭 resultados", "la página estaba a medio cargar; mirada otra vez")
            items = _retry
    # V2-323 — Y SI AUN ASÍ NO HAY NI UNA FILA CON NOMBRE, puede que la página no las haya PINTADO.
    # V2-294 (arriba) decidió a propósito no reintentar con cero filas, porque «esa sí puede ser una
    # página sin resultados». Cierto, y con un punto ciego: un listado VIRTUALIZADO no crea sus fichas
    # hasta que te acercas a ellas. Medido contra la URL exacta que condujo un worker
    # (`autoscout24.es/lst/cit_madrid/ft_diesel?…`, 2026-08-25): 0 anclas de anuncio sin desplazarse y
    # 40 tras hacerlo — 1 fila contra 19. La ronda reportó hoja vacía tras cuatro minutos de navegación
    # real, que es indistinguible de «la página no tenía nada».
    #
    # `materialise_below_the_fold` NO invalida el argumento de coste de V2-294, lo respeta: solo se mueve
    # si la página es más alta que la pantalla, y una búsqueda de verdad vacía no llega ni a una (0,2×
    # medido en wallapop, frente a 11,5× aquí). La vista vuelve a su sitio, y las fichas materializadas
    # sobreviven a la vuelta — comprobado.
    if not _f.by_identity(items)[0] and await _lazy.materialise_below_the_fold(tb.page):
        _tarde = await tb.extract_listings(_limit)
        if _f.by_identity(_tarde)[0]:
            _f._emit_nav(task_id, "🧭 resultados",
                      "la página pintaba sus fichas al acercarse; recorrida y mirada otra vez")
            items = _tarde
    # Se CUENTAN los que tienen nombre. Decir «12 resultados» cuando nueve son enlaces de categoría es
    # una cifra que el operador lee y se cree; y `found(0)` no calla —dice «sin resultados en esta
    # página»—, que es justo lo que hace falta para que el worker cambie de sitio en vez de insistir.
    _named, _unnamed = _f.by_identity(items)
    _extra = f" (+{len(_unnamed)} enlaces sin nombre)" if _unnamed else ""
    _f._emit_nav(task_id, "🧭 resultados", f"{len(_named)} anuncios/resultados en la página{_extra}")
    _f._say_phase(task_id, _progress.found(len(_named)))   # V2-227 B1: «12 resultados», el hito que pidió
    _f._hand_over(task_id, items)      # V2-223: a la hoja y a la conversación, no solo al worker
    return {"ok": True, "listings": items, "n": len(items), **_door.take(_f._sheet_of(task_id)), "url": str(getattr(tb.page, "url", "") or "")}  # V2-798: the SOURCE


@_f.router.post("/api/navegador/act")
async def navegador_act(task_id: str = Body(..., embed=True), action: str = Body(..., embed=True),
                        args: dict = Body(default_factory=dict, embed=True)):
    """Execute one browser action in the `task_id` tab and return resulting state so the agent can reason about the
    next step. Actions: snapshot | navigate{url} | click{ref} | type{ref,text,submit} | scroll{dy} | press{key} |
    extract{limit}. `click`/`type` use refs from the latest snapshot, so request snapshot before acting. The owner's
    confirmation gate for irreversible actions still applies. Best-effort: never raises."""
    action = (action or "").strip()
    args = args or {}
        # V2-343: every browser action says what it is in the Process tab. It deliberately comes BEFORE execution:
        # the operator needs «entrando en coches.net» WHILE entering, not afterward. If the action fails, the
        # failure already has its own row (`🧭 navegador ⚠️ error`) and waiting line.
    _f._say_phase(task_id, _f._phase_for_action(action, args))
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
            return {"ok": True, "shot": _f._shot_path(task_id), **_f._with_stall(task_id, _f._with_wall(snap, task_id))}
        if action == "look":
            # V2-049 VISION: fresh viewport capture to disk. The worker reads it with its Read tool, sees the page
            # like a human, and acts by coordinates (click_at/type_at). This is the robust path for forms,
            # date-pickers, and selects that the text snapshot cannot describe well enough.
            await tb._capture()
            snap = {}
            try:
                snap = await tb.snapshot_for_agent()
            except Exception:
                pass
            _f._emit_nav(task_id, "🧭 vista", f"captura {snap.get('title') or snap.get('url') or ''}"[:200])
            return {"ok": True, "shot": _f._shot_path(task_id), "viewport": {"width": 1280, "height": 800},
                    **_f._with_stall(task_id, _f._with_wall(snap, task_id))}
        if action == "visit":
            # READ ONE LISTING WITHOUT LOSING THE LIST. It comes before `extract` because they share the idea of
            # «what is on this page», but not the tab: `visit` opens its own and closes it.
            got = await tb.visit(str(args.get("url", "")), int(args.get("chars", 2500)))
            if got.get("ok"):
                _f._emit_nav(task_id, "🧭 ficha", f"{str(got.get('title') or got.get('url'))[:150]}")
            else:
                _f._emit_nav(task_id, "🧭 ficha ⚠️ error", str(got.get("error"))[:150])
            return got
        if action == "extract":
            return await _f._act_extract(tb, task_id, args)
        if action in ("navigate", "click", "type", "select_option", "scroll", "press", "click_at", "type_at"):
            # La dirección de ANTES, para poder contar qué cambió (V2-293). Se lee del registro de la pestaña
            # porque es lo único que sobrevive entre invocaciones del puente: `nav_cli` es un proceso por acción.
            _before = ""
            try:
                from widgets.navegador import tasks as _t0
                _before = str((_t0.get(task_id) or {}).get("url") or "")
            except Exception:
                pass
            ok, msg = await tb.agent_act(action, args)
            # Return fresh state after the action so the agent sees the result and decides the next step.
            snap = {}
            try:
                snap = await tb.snapshot_for_agent()
            except Exception:
                pass
            # Observability: which page the action reached (title + url); only the browser knows this (V2-048).
            page = " · ".join(x for x in (str(snap.get("title") or "").strip(),
                                          str(snap.get("url") or "").strip()) if x)
            if page:
                _f._emit_nav(task_id, "🧭 página", page)
            # Fresh PNG path; every action calls _capture, so the worker can Read the view after acting.
            return {"ok": bool(ok), "msg": msg, "shot": _f._shot_path(task_id),
                    **_f._with_stall(task_id, _f._with_wall(_f._with_url_change(_before, snap), task_id))}
        return JSONResponse({"ok": False, "error": f"acción desconocida: {action}"}, status_code=400)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": f"{type(e).__name__}: {_brief(e, 160)}"},
                            status_code=500)
