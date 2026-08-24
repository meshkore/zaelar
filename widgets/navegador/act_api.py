"""widgets/navegador/act_api.py: BROWSER BRIDGE for Claude Code agents (V2-036 F3).

Exposes the owner's `TaskBrowser` primitives as a synchronous request/response API so a headless Claude Code agent
can drive zaelar's Chromium step by step (navigate/click/type/scroll/snapshot/extract) with its own intelligence.
This replaces the cheap DOM->vision loop. It runs in the uvicorn loop, the same loop as the backed browser
owner, so it can call `TaskBrowser` methods directly rather than through the fire-and-forget mailbox. Invoked by
the `nucleo/nav_cli.py` CLI (`hbweb`). Local/loopback: same trust model as the rest of the API.
"""
import asyncio

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

# Lo que se espera antes de volver a mirar una página que devolvió solo filas huecas (V2-294). Corto a propósito:
# es el tiempo de hidratación de un listado, no una espera de red — si en eso no ha pintado, mirar más no arregla
# nada y el worker tiene sus propias salidas (cambiar de búsqueda, de sitio).
_HYDRATE_WAIT_S = float(__import__("os").environ.get("ZAELAR_NAV_HYDRATE_S", "2") or 2)


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


def _query_of(url: str) -> dict:
    """Los PARÁMETROS de la dirección, tal cual. Un listado codifica sus filtros ahí — cualquiera, no uno."""
    try:
        from urllib.parse import parse_qsl, urlsplit
        return {k: v for k, v in parse_qsl(urlsplit(str(url or "")).query, keep_blank_values=True)}
    except Exception:
        return {}


def _with_url_change(before: str, snap: dict) -> dict:
    """Decirle al worker QUÉ cambió en la dirección de la página, no solo cuál es ahora.

    V2-293 — medido en la tanda de las 13:42, `search-buy-guitar__es`, con el modelo conduciendo a ciegas (el
    escalón que servía la sesión no lee imágenes, V2-289). El worker quería precio MÁXIMO 150 €: pulsó el filtro,
    escribió «150»… y la página se fue a `?min_sale_price=750`. Precio MÍNIMO, y de 750. La ronda acabó ahí con
    CERO extracciones, y nada en la respuesta del puente decía que el filtro hubiera caído en otro sitio: la URL
    entera viaja en una línea larga entre el título y los elementos, y un parámetro nuevo dentro de ella no se ve.

    Lo que se añade es el DELTA, que es lo único que el worker no puede deducir: la URL de ahora la tiene, la de
    antes no. Y es genérico por construcción — se comparan los parámetros que haya, sin saber de qué sitio son ni
    qué significan; el mismo mecanismo sirve para un filtro de precio, uno de talla o una página siguiente.

    Deliberadamente NO se juzga si el cambio es el que quería: eso es del worker, que es quien sabe qué pidió.
    Aquí se dice lo que la página afirma de sí misma.
    """
    a, b = _query_of(before), _query_of(str((snap or {}).get("url") or ""))
    if not before or a == b:
        return snap
    bits = []
    for k, v in b.items():
        if k not in a:
            bits.append(f"{k}={v} (nuevo)")
        elif a[k] != v:
            bits.append(f"{k}: {a[k]} → {v}")
    for k in a:
        if k not in b:
            bits.append(f"{k} ya no está")
    if not bits:
        return snap
    snap = dict(snap or {})
    snap["url_change"] = "; ".join(bits[:6])
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


def by_amount(items) -> tuple:
    """Split NAMED rows into (rows you can act on, hollow ones), keeping the relative order inside each half.

    Sibling of `by_identity`, one layer deeper and for the same reason. That one asked «does this row have a
    name?»; this one asks «does it carry anything to act on?» — a real amount, or a number to call. A row with a
    name, no amount and no phone is a listing whose price never painted, or one that publishes none: it is not a
    candidate for «un monitor de 27 pulgadas por menos de 150 €», and it must not take one of the three slots the
    note offers.

    Measured on the batch of 2026-08-24 14:10, `search-secondhand-monitor__es`: the browser found ten rows, the
    first four priced `0 €` («Monitores», «Monitor SAMSUNG», «Monitor de Hípica», «Baby monitor») and below them
    two real `Monitor MSI MAG 27" 280Hz` at 100 € — both under the cap, both the right size. `head` took the
    first three in DOM order, so what reached the operator was the three without a price, one of them a
    horse-riding monitor, while the two that answered the errand sat under the cut. Same shape in
    `search-buy-bicycle__es` at 14:40: `Bicicleta Orbea 0 €` ranked third, ahead of bikes at 190/180/150 €.

    A ZERO IS NOT A PRICE HERE and that is the whole test: any digit other than zero counts as an amount, which
    needs no locale and survives the decimal separator this extractor deliberately does not reconstruct
    («169 00 €» → digits `16900` → an amount). It is a PARTITION, not a ranking — nothing is dropped, and the
    hollow rows keep their order and still reach the sheet.

    It cannot hurt the class it does not apply to: on a directory of plumbers or barbers no row carries a price,
    so one half comes out empty and the order is exactly what it was. V2-240 stands — a result is a name and a
    way to act on it, never a price — which is why a phone counts as much as an amount.
    """
    withs, hollow = [], []
    for it in (items or []):
        if not isinstance(it, dict):
            continue
        digits = "".join(c for c in str(it.get("price") or "") if c.isdigit())
        actionable = any(c != "0" for c in digits) or bool(str(it.get("tel") or "").strip())
        (withs if actionable else hollow).append(it)
    return withs, hollow


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
        # V2-295 — con nombre e IMPORTE delante de con nombre y sin nada. Ver `by_amount`: `head` ofrecía las
        # tres primeras en orden de DOM, y ahí es donde caen las fichas cuyo precio no llegó a pintar.
        priced, hollow = by_amount(named)
        named = priced + hollow
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
        # LA COSECHA, en números (V2-296). Todas estas cifras ya estaban calculadas aquí arriba y se gastaban en
        # una frase; el operador pidió verlas. UN solo sitio para contarlas —aquí, donde las dos mitades de cada
        # corte están vivas a la vez— y protegido de contar dos veces la misma página por `_HANDED`.
        try:
            _t.tally(task_id, pages=1, rows=len(items), repeated=repeated, unnamed=len(unnamed),
                     hollow=len(hollow), kept=len(priced), offered=len(head))
        except Exception:  # noqa: BLE001
            pass
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
            if items and not by_identity(items)[0]:
                await asyncio.sleep(_HYDRATE_WAIT_S)
                _retry = await tb.extract_listings(_limit)
                if by_identity(_retry)[0]:
                    _emit_nav(task_id, "🧭 resultados", "la página estaba a medio cargar; mirada otra vez")
                    items = _retry
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
                _emit_nav(task_id, "🧭 página", page)
            # Fresh PNG path; every action calls _capture, so the worker can Read the view after acting.
            return {"ok": bool(ok), "msg": msg, "shot": _shot_path(task_id),
                    **_with_stall(task_id, _with_wall(_with_url_change(_before, snap), task_id))}
        return JSONResponse({"ok": False, "error": f"acción desconocida: {action}"}, status_code=400)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": f"{type(e).__name__}: {_brief(e, 160)}"},
                            status_code=500)
