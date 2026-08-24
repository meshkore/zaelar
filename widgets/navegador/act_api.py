"""widgets/navegador/act_api.py: BROWSER BRIDGE for Claude Code agents (V2-036 F3).

Exposes the owner's `TaskBrowser` primitives as a synchronous request/response API so a headless Claude Code agent
can drive zaelar's Chromium step by step (navigate/click/type/scroll/snapshot/extract) with its own intelligence.
This replaces the cheap DOM->vision loop. It runs in the uvicorn loop, the same loop as the backed browser
owner, so it can call `TaskBrowser` methods directly rather than through the fire-and-forget mailbox. Invoked by
the `nucleo/nav_cli.py` CLI (`hbweb`). Local/loopback: same trust model as the rest of the API.
"""
from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse
from nucleo.errors import brief as _brief

router = APIRouter()


def _shot_path(task_id: str) -> str:
    """Absolute PNG path for this tab's viewport, written by TaskBrowser._capture after each action, so the worker
    can read it with Read. Best-effort: if anything fails, return '' and the worker continues with text snapshot.

    V2-205 — it used to return the path whether or not the PNG was THERE, and `nav_cli` turns a non-empty value
    into an instruction: «MÍRALA con Read "<path>"». So every action taken before the first successful capture
    —or after one that failed— sent the worker to read a file that does not exist. Measured in two independent
    runs (`find-theatre-tickets__es` 15:06, and the same family reported on `cheapest-monitor`):

        worker/task «📄 archivo ⚠️ error»: File does not exist.
        Note: your current working directory is /private/var/.../T/zaelar-workers/2

    The path was never the problem — it is absolute, and V2-117 confirmed the CLI already allows reading outside
    the working directory. What was wrong is ADVERTISING it. The text snapshot is the documented fallback right
    here in this docstring; an empty return takes it, and `nav_cli` simply prints no VISTA line.
    """
    try:
        import os
        from widgets import store
        from widgets.navegador import owner
        p = os.path.abspath(f"{store.data_dir(owner.WID)}/shot-{task_id}.png")
        return p if os.path.isfile(p) else ""
    except Exception:
        return ""


def _emit_nav(nav_tid: str, label: str, text: str) -> None:
    """V2-048: observability row for a browser action result: which page it reached / what it found. This is what
    the command itself does NOT say and only the browser knows. Label differs from the intent `step`, avoiding
    collisions with `navegador` flood-dedup. Stamps trace/span for the worker owning the tab. Best-effort, never
    raises."""
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


# Same threshold the FlashBrain turn uses for «sin moverse» (`nucleo/flash/prompt.py`), read from the same env
# var so the two halves of one fact can never drift apart.
_STALL_HINT_S = int(__import__("os").environ.get("ZAELAR_NAV_STALLED_S", "120") or 120)


def _with_wall(snap: dict, task_id: str = "") -> dict:
    """Annotate a snapshot with `wall` when the page it landed on STOPPED us (anti-bot challenge, CAPTCHA, load
    error) — V2-167.

    The worker drives through this endpoint and its only view of the page is what comes back here, so a wall it
    cannot see is a wall it grinds against. Measured: a run spent three minutes re-photographing Booking's
    `chal_t=` challenge and another walked through Google's `/sorry/index`, and both reported no obstacle at all.
    The rule telling the worker what to do about a captcha already existed (`nucleo/dispatch_prompts.py`); what
    was missing was any way for it to know it was looking at one.
    """
    try:
        from widgets.navegador import tasks as _t
        reason = _t.wall_reason(str((snap or {}).get("url") or ""))
    except Exception:
        return snap
    if reason:
        snap = dict(snap or {})
        snap["wall"] = reason
        # V2-213 — «prueba otro sitio» sin decir CUÁL es un deseo, no una instrucción. Medido: trece minutos en
        # el mismo host en `book-hotel-night-known__es`, y `restaurant-tonight-madrid` acabando en una página de
        # resultados de DuckDuckGo. El catálogo genético sabe a qué categoría pertenece el encargo y ahora
        # también dónde ir cuando el sitio de confianza nos cierra la puerta; el host que acaba de bloquearnos se
        # EXCLUYE, porque ofrecer el sitio donde está atascado se lee como «insiste».
        try:
            from nucleo.flash import site_catalog as _sc
            from widgets.navegador import tasks as _t2
            goal = str((_t2.get(task_id) or {}).get("goal") or "") if task_id else ""
            alts = _sc.alternatives_for(goal, _t.host_of(str(snap.get("url") or "")))
            if alts:
                snap["wall_alts"] = [{"name": n, "url": u} for n, u in alts[:3]]
        except Exception:
            pass
    return snap


def _with_stall(task_id: str, snap: dict) -> dict:
    """Tell the worker how long its own task has gone WITHOUT MOVING — the half of V2-167 that never reached it.

    The wall travels to the worker (above) and the stall did not, which left the two halves of the same fact in
    different places: the FlashBrain turn learned that a task had stopped moving, and the only party that could
    do anything about it did not.

    Measured on `find-theatre-tickets__es` (2026-08-20 01:01): the worker navigated seven times, landed on the
    right event page at 00:40:32, and then took FOURTEEN screenshot revisions of it without a single further
    navigation for roughly twenty minutes. It was not blocked and it was not idle — it was looking at the page
    over and over. Nothing in what came back from here said «you have been here a while», so from inside the
    loop every `look` was as good as the first. Same shape on `restaurant-tonight-madrid`: eleven minutes and
    ten captures of one page.

    Only reported past the same threshold the turn uses, so an ordinary page-by-page pass says nothing.
    """
    try:
        from widgets.navegador import tasks as _t
        stalled = int((_t.get(task_id) or {}).get("stalled_s") or 0) if hasattr(_t, "get") else 0
        if not stalled:
            for _p in _t.active_progress():
                if str(_p.get("id") or "") == str(task_id):
                    stalled = int(_p.get("stalled_s") or 0)
                    break
    except Exception:
        return snap
    if stalled >= _STALL_HINT_S and not (snap or {}).get("wall"):
        snap = dict(snap or {})
        snap["stalled_s"] = stalled
        snap["hint"] = (f"llevas {stalled // 60} min en esta página sin avanzar: o extraes ya lo que necesitas "
                        f"de lo que tienes delante, o pruebas otro sitio. Repetir `look` no la cambia.")
    return snap


from nucleo.workers import progress as _progress   # V2-227: la frase que lee una persona

_HANDED: dict[str, str] = {}          # V2-223: última extracción entregada por tarea (no repetir la misma)


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


def by_identity(items) -> tuple:
    """Parte lo extraído en (CON nombre, SIN nombre), conservando el orden relativo dentro de cada mitad.

    Una fila sin título no es un resultado: es cromo de navegación —un enlace de categoría, un filtro de precio—
    y sale ANTES que las fichas de producto porque ese es el orden del DOM en cualquier listado, no la mala
    suerte de una tienda concreta. Medido en `cheapest-monitor` (2026-08-20 23:44): el navegador sacó seis filas,
    las tres primeras eran «portátiles hasta 799 €», «móviles menos de 200 €» y «tablets hasta 200 €» sin título,
    y las tres siguientes eran monitores REALES a 99 € con enlace de producto y foto. La nota se llenaba con
    `items[:3]` en orden de DOM, así que al cerebro le llegaron las tres primeras y ninguna de las buenas — y el
    turno describió fielmente lo único que tenía: «lo que ha sacado la página son categorías genéricas de
    portátiles, móviles y tablets, no monitores».

    ES UN PARTIDO, NO UNA ORDENACIÓN, y la diferencia importa: no se juzga cuál es mejor —eso es del cerebro, y
    `observability/evidence.py` prohíbe interpretar por buenas razones—, se separa por un hecho estructural,
    tener nombre o no tenerlo. Y NO se tira nada: lo de abajo se cuenta y se dice.

    Tampoco es una lista negra de patrones. Mañana es otra tienda; «tiene nombre» vale para un hotel, un coche,
    un piso en Los Ángeles o una entrada de teatro, y para el listado que nadie ha escrito todavía.
    """
    named, unnamed = [], []
    for it in (items or []):
        if not isinstance(it, dict):
            continue
        (named if str(it.get("title") or "").strip() else unnamed).append(it)
    return named, unnamed


def dedupe_by_url(items) -> tuple:
    """La MISMA url no es dos hallazgos. Devuelve (lista sin repetidos, cuántos se colapsaron).

    Medido por el arnés en la misma ronda del monitor: la segunda nota llevaba tres filas y las tres eran
    `aax-eu-zaz.amazon.es/x/c/JLv…` — la misma url de anuncio repetida. O sea que las repeticiones no solo
    ensucian: OCUPAN el cupo de tres, así que dos de los tres huecos se gastaban en decir lo mismo.

    No es interpretar (que es lo que `observability/evidence.py` prohíbe, con razón): dos filas con la misma
    dirección son la misma página, y enseñar tres veces la misma no informa tres veces. Se conserva la PRIMERA
    aparición —el orden manda hasta que se demuestre lo contrario— y una fila SIN url no se deduplica contra
    nada: la ausencia de dirección no es una identidad compartida.
    """
    out, seen, dropped = [], set(), 0
    for it in (items or []):
        u = str((it or {}).get("url") or "").strip()
        if u and u in seen:
            dropped += 1
            continue
        if u:
            seen.add(u)
        out.append(it)
    return out, dropped


def _sheet_of(task_id: str) -> str:
    """La hoja del encargo al que pertenece esta pestaña (V2-259). Fail-soft a "" = la hoja de siempre.

    V2-281 — se le pregunta a la PESTAÑA primero, porque es la que sobrevive. Esto resolvía SOLO por el
    registro de sesiones vivas, y una pestaña dura más que el worker que la abrió: el record se saca en el
    `finally` de `_run_session` y un relevo abre otro. Así que un hallazgo que llega después resolvía a "" y
    caía en la hoja PELADA — 24 filas ahí contra 12 en la del encargo, para UN encargo (medido en
    `search-secondhand-monitor__es`, 2026-08-24 01:47), y esa caja huérfana es además la «tarjeta fantasma»
    que el canvas lleva rondas reportando.

    El registro se conserva como respaldo, no por simetría: una pestaña creada antes de este cambio no lleva
    sello, y mientras su worker viva el registro sí sabe contestar.
    """
    try:
        from widgets.navegador import tasks as _t
        own = str(((_t.get(task_id) or {}).get("sheet")) or "").strip()
        if own:
            return own
    except Exception:  # noqa: BLE001
        pass
    try:
        from nucleo import dispatch as _disp
        return _disp.sheet_for_nav_task(task_id)
    except Exception:  # noqa: BLE001
        return ""


def _hand_over(task_id: str, items: list) -> None:
    """What the browser EXTRACTED goes to the results sheet AND to the conversation — not only to the worker.

    V2-223. Measured by the harness on `hotel-under-15-days` (sandbox `20260820-194231`), and this is the whole
    case in five lines of its stream:

        19:44:00  navigate → booking.com/searchresults?ss=Sevilla&checkin=…&group_adults=2   (parameters PERFECT)
        19:44:39  extract  → one result, and it was an ad: «Experiencia Premium en el Teatro Flamenco», € 25
        19:44:47  pivoted to Google Hotels on its own
        19:45:29  extract  → «Exe Sevilla Macarena», «65 €», with a URL          ← THE ANSWER EXISTED
        19:45:45  turn 7   → «¡De nada! Sigo pendiente y te digo en cuanto tenga algo.»

    Sixteen seconds. The prompt of that turn contains neither «Exe Sevilla» nor «Macarena» nor «65 €», and the
    run reported `missing_signals: ['widget']` — so it was not in the sheet either. The result went to the
    worker's stdout and died there: `set_results` was only ever called by `dispatch._finalize_web`, at the END of
    the session, re-extracting whatever page happened to be on screen by then. Here the round ran out of turns
    first, so nobody was ever told about a hotel we had actually found.

    It travels as a PUSHED note rather than a prompt line for the reason the harness measured with a
    side-by-side counter in this same case: pushed system notes are said in the next turn 3 out of 3, prompt
    status lines 0 out of 13 (see `nucleo/dispatch.recently_ended_sessions` for why that 0/13 was not simple
    disobedience).

    JUDGEMENT stays with the brain, deliberately: the FIRST extraction here was an ad, so a note that ordered
    «announce this» would have had it offering a €25 flamenco show as the hotel. The note hands over the facts
    and names the test.

    V2-226 — and the note is ONE order, not three. As first written it said «if it answers, give it; if not,
    don't offer it as a result; but then don't say you're still searching either». Measured on the first clean
    round (2026-08-20 20:23, sha `0b89510`): the browser had extracted the €25 flamenco show and the turn said
    «se ha quedado a medias y no ha llegado a darme resultados». It obeyed the middle clause and dropped the
    last one — with a result in front of it, it reported none. That is the same shape V2-224 had just measured
    on the other block: two orders in one sentence resolve by coin flip. So the fork became a qualifier inside a
    single imperative —NAME it this turn, and in the same sentence say whether it serves— and the sentence that
    can never be true («no hay resultados») is banned outright rather than implied.
    """
    if not items:
        return
    try:
        fresh, repeated = dedupe_by_url(items)
        named, unnamed = by_identity(fresh)
        ordered = named + unnamed          # lo que TIENE identidad va delante; nada se descarta
        sig = "|".join(f"{(i or {}).get('title', '')}~{(i or {}).get('price', '')}~{(i or {}).get('tel', '')}"
                       for i in ordered[:5])
        if _HANDED.get(task_id) == sig:      # re-extracting the same page is not a new finding
            return
        _HANDED[task_id] = sig
        from widgets.navegador import tasks as _t
        prev = (_t.get(task_id) or {}).get("results") or {}
        # El HECHO se queda en la tarea: `has_results` es lo que deja al turno decir «ya trajo algo» en vez de
        # elegir entre «sigue viva» y «está bloqueada» (V2-192/V2-200). Lo que cambia en V2-257 es que la tarjeta
        # ya no lo PINTA — el hecho no es una superficie.
        _t.set_results(task_id, {"conclusion": (prev or {}).get("conclusion") or "", "items": ordered[:5]})
        # …y los HALLAZGOS van a la hoja, que es donde el operador los está esperando desde que se abrió sola al
        # encargar. Una sola puerta para los tres caminos (V2-257).
        try:
            from widgets.results import intake as _intake
            _intake.push(ordered, sheet=_sheet_of(task_id),
                         source_url=str((_t.get(task_id) or {}).get("url") or ""))
        except Exception:  # noqa: BLE001
            pass
        goal = str((_t.get(task_id) or {}).get("goal") or "la tarea del navegador")[:70]

        def _one(i: dict) -> str:
            # V2-240 — el TELÉFONO viaja con la fila. Extraerlo y dejarlo caer aquí sería el defecto de V2-236 otra
            # vez: el dato existe, nadie lo ve. En un encargo de servicio es el dato que RESUELVE («llama a este
            # número»), y el que separa una ficha de negocio del enlace a un directorio.
            bits = [str(i.get("title") or "").strip()[:80], str(i.get("price") or "").strip()[:24],
                    str(i.get("tel") or "").strip()[:24], str(i.get("url") or "").strip()[:120]]
            return " — ".join(b for b in bits if b)

        # La CABECERA de la nota son las que tienen nombre. Con ninguna, va lo que hay: callarse porque solo
        # salieron enlaces de categoría dejaría al turno sin poder decir «esta página solo me da categorías,
        # cambio de sitio», que es una respuesta ÚTIL y cierta.
        head = (named or unnamed)[:3]
        listing = "; ".join(_one(i) for i in head)
        # Nunca se pierde EN SILENCIO la información de que había más (doctrina de `observability/evidence.py`).
        left = len(ordered) - len(head)
        bits = []
        if left > 0:
            bits.append(f"{left} fila{'s' if left != 1 else ''} más")
        if repeated:
            bits.append(f"{repeated} repetida{'s' if repeated != 1 else ''}")
        tail = f" (y {' y '.join(bits)} de la misma página)" if bits else ""
        if named:
            body = (f"El navegador ha SACADO esto de la página, trabajando en «{goal}»: {listing}{tail}. Nadie "
                    f"más lo sabe: no está en la conversación hasta que tú lo digas, así que NO puedes decir "
                    f"que no hay resultados ni que sigues buscando sin más. NÓMBRALO EN ESTE TURNO y, en la "
                    f"misma frase, di si sirve: si responde a lo que pidió el operador, dáselo como resultado "
                    f"con nombre, precio y enlace; si es otra cosa —un anuncio, un producto distinto—, nómbralo "
                    f"igual y di por qué no sirve y qué haces ahora.")
        else:
            # Ni una fila con nombre: lo que la página dio son enlaces de navegación, no resultados. Se dice
            # tal cual, con la salida delante, en vez de servirlos como si fueran hallazgos.
            body = (f"El navegador ha leído la página trabajando en «{goal}» y NO ha sacado ni un resultado con "
                    f"nombre: solo enlaces de navegación de la propia web ({listing}{tail}). DÍSELO EN ESTE "
                    f"TURNO con tus palabras —esa página no está dando lo que pidió— y di qué haces ahora; no "
                    f"los ofrezcas como si fueran resultados ni digas que sigues buscando sin más.")
        from voice import brain_notes
        brain_notes.push("[SISTEMA] " + body)
    except Exception:  # noqa: BLE001
        pass


@router.post("/api/navegador/act")
async def navegador_act(task_id: str = Body(..., embed=True), action: str = Body(..., embed=True),
                        args: dict = Body(default_factory=dict, embed=True)):
    """Execute one browser action in the `task_id` tab and return resulting state so the agent can reason about the
    next step. Actions: snapshot | navigate{url} | click{ref} | type{ref,text,submit} | scroll{dy} | press{key} |
    extract{limit}. `click`/`type` use refs from the latest snapshot, so request snapshot before acting. The owner's
    confirmation gate for irreversible actions still applies. Best-effort: never raises."""
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
            return {"ok": True, "shot": _shot_path(task_id), **_with_stall(task_id, _with_wall(snap, task_id))}
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
            _emit_nav(task_id, "🧭 vista", f"captura {snap.get('title') or snap.get('url') or ''}"[:200])
            return {"ok": True, "shot": _shot_path(task_id), "viewport": {"width": 1280, "height": 800},
                    **_with_stall(task_id, _with_wall(snap, task_id))}
        if action == "extract":
            items = await tb.extract_listings(int(args.get("limit", 14)))
            # Se CUENTAN los que tienen nombre. Decir «12 resultados» cuando nueve son enlaces de categoría es
            # una cifra que el operador lee y se cree; y `found(0)` no calla —dice «sin resultados en esta
            # página»—, que es justo lo que hace falta para que el worker cambie de sitio en vez de insistir.
            _named, _unnamed = by_identity(items)
            _extra = f" (+{len(_unnamed)} enlaces sin nombre)" if _unnamed else ""
            _emit_nav(task_id, "🧭 resultados", f"{len(_named)} anuncios/resultados en la página{_extra}")
            _say_phase(task_id, _progress.found(len(_named)))   # V2-227 B1: «12 resultados», el hito que pidió
            _hand_over(task_id, items)      # V2-223: a la hoja y a la conversación, no solo al worker
            return {"ok": True, "listings": items, "n": len(items)}
        if action in ("navigate", "click", "type", "select_option", "scroll", "press", "click_at", "type_at"):
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
                _emit_nav(task_id, "🧭 página", page)
            # Fresh PNG path; every action calls _capture, so the worker can Read the view after acting.
            return {"ok": bool(ok), "msg": msg, "shot": _shot_path(task_id), **_with_stall(task_id, _with_wall(snap, task_id))}
        return JSONResponse({"ok": False, "error": f"acción desconocida: {action}"}, status_code=400)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": f"{type(e).__name__}: {_brief(e, 160)}"},
                            status_code=500)
