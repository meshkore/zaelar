"""What a Brain Worker session is PREPARED with: the brief, the errand's name, the web task's sheet and its
finishing, and the memory context (V2-778 F1, 2026-10-01).

Moved out of `nucleo/dispatch.py` with no behaviour change. Every module-level name these functions read — each
other included — is read through the dispatcher (`_d.<name>`), so a patch on `nucleo.dispatch` still governs every
call, and the dispatcher imports them back under their names.
"""
from __future__ import annotations

from nucleo import dispatch as _d


async def _compose_brief(request: str, context: str, trusted: bool, resume: dict | None = None) -> dict | None:
    """PRE-VUELO of a research: convierte the request cruda in a BRIEF dirigido (nucleo/research.py).

    Por what esta AQUÍ and no in the turn of voice: dirigir bien a search —separar criterios duros of blandos,
    add it that a experto sabe that hara missing, fijar cuan wide there is that buscar and with what baremo juzgar— es a
    work of razonamiento, and the FlashBrain of voice has that contestar in milisegundos. Aqui already estamos outside of
    ese reloj: the escalada es asincrona, the operator already sabe that esto tarda, so that this es the only point of the
    sistema donde is can pensar before of empezar a trabajar.

    If es a REANUDACIÓN, the brief of the ronda anterior is reuses tal cual: the criterios already estaban acordados
    and recomponerlos podria cambiarlos a mitad of a search that the operator cree that continues the same guion."""
    if not trusted:
        return None                       # perfil sin tools: no hay investigación que dirigir
    prev_tid = str((resume or {}).get("brief_task") or "")
    if prev_tid:
        prev = _d.research.load(prev_tid)
        if prev:
            return prev
    # ¿Ya investigamos esto and the operator vuelve a the load? Entonces es the RONDA SIGUIENTE of the same search:
    # hereda the criterios acordados and sube the amplitud, with su frase of ahora como reason of the rechazo. Sin esto,
    # «esos no me valen, busca mas» recomponia the brief from cero and repetia the same search with the same
    # amplitud — the operator habria visto arrive the same results and concluido, with razon, that no le escuchamos.
    gk = _d._goal_key(request)
    prev = _d.research.previous_round(gk)
    if prev:
        nxt = _d.research.expand(prev, note=request)
        _d.logger.info(f"dispatch: RONDA {nxt.get('round')} de una investigación ya conocida "
                    f"(≥{(nxt.get('breadth') or {}).get('min_candidates')} candidatos): {request[:60]}")
        return nxt
    return await _d.research.compose(request, context)


#: Live references to the errand NAMERS (V2-530), for the same reason the brief composers below need one: a
#: bare `Task` can be garbage-collected mid-flight and die in silence.
_TITLE_BG_TASKS: set = set()


def _name_errand(rec) -> None:
    """Give this errand its NAME, without anybody waiting for it (V2-530).

    Fire-and-forget on purpose. The sheet is already on screen under the brief, the worker is already spawning,
    and the voice already answered — so the only thing a slow or dead provider can cost here is a box that
    keeps the name it already had. That is why nothing upstream checks the result.
    """
    try:
        from nucleo import errand_title as _et
        if not _et.enabled() or not (rec.goal or "").strip():
            return

        async def _go():
            try:
                t = await _et.compose(rec.goal)
            except Exception:  # noqa: BLE001
                return
            if not t or t == (getattr(rec, "title", "") or ""):
                return
            rec.title = t
            try:
                from voice.observer import emit
                emit("task", "🏷️ encargo nombrado", text=t, role="system",
                     extra={"id": rec.task_id, "goal": (rec.goal or "")[:120]})
            except Exception:
                pass
            if _d.surfaces.opens_sheet(getattr(rec, "surface", "")):
                _d._sheet_retitle(rec)
            elif _d.surfaces.opens_doc(getattr(rec, "surface", "")):
                _d._docsheet.doc_retitle(rec)
            try:
                from nucleo import tasks as _tasks
                _tasks.retitled(rec)   # V2-728 — the durable row carries the name the operator will search by
            except Exception:  # noqa: BLE001
                pass
            _d.sync_state()

        _t = _d.asyncio.ensure_future(_go())
        _d._TITLE_BG_TASKS.add(_t)
        _t.add_done_callback(_d._TITLE_BG_TASKS.discard)
    except Exception:  # noqa: BLE001
        pass


#: Referencias live a compositores in second plano (V2-301): a Task without referencia can ser recolectado a
#: mitad, and this dies in silencio — the clase of failure that leaves al worker without address without that nothing avise.
_BRIEF_BG_TASKS: set = set()


def _attach_brief_followup(task: "_d.asyncio.Task", *, key: str, rec: "_d.SessionRecord", req: str,
                           kind0: str) -> None:
    """V2-301 — the second half of the parallel brief. When the composer finishes AFTER the worker already
    spawned, its direction still has to do everything the serial path did: persist/seed the brief, promote a
    `generic` task to the research budget (direction proves it IS an investigation), and reach the RUNNING
    worker — as an injected turn, through the same channel every mid-task refinement already uses (V2-038).

    The callback runs in the owner loop (the composer task was created there), so `ensure_future` is safe.
    A composer that dies here changes nothing for the worker — it is already running, which is exactly the
    fail-open the serial path promised («the worker starts SIN brief»); only the budget promotion is still
    honoured, same as the serial ComposerUnavailable branch.
    """
    _d._BRIEF_BG_TASKS.add(task)

    def _done(t: "_d.asyncio.Task") -> None:
        _d._BRIEF_BG_TASKS.discard(t)
        b, unavailable = None, False
        try:
            b = t.result()
        except (_d.research.ComposerUnavailable, _d.asyncio.CancelledError):
            unavailable = True
        except Exception:  # noqa: BLE001
            unavailable = True
        try:
            if b:
                _d.research.save(key, b)
                _d.research.remember_round(_d._goal_key(req), b)
                if not _d.surfaces.opens_doc(getattr(rec, "surface", "")):    # V2-644: no results sheet to seed
                    _d.asyncio.ensure_future(_d._seed_research_criteria(b))
                block = _d.research.to_prompt_block(b)
                if block and rec.status in _d.LIVE_SESSION_STATES:
                    _d.inject_soon(key, ("Ya está compuesta la DIRECCIÓN de tu investigación — aplícala DESDE "
                                      "AHORA a lo que estás haciendo, sin reempezar lo ya andado:\n\n" + block))
            # La promocion of budget va with brief O with compositor caido (same two ramas that the camino
            # serial); a compose that returns None a secas said «esto no es a research» and no promociona.
            if (b or unavailable) and kind0 == "generic" and rec.kind == "generic":
                rec.kind = "research"
                rec.label = _d._default_label("research", req)
                _d.logger.info(f"dispatch: tarea {key} promocionada a research por el brief tardío")
                _d.sync_state()
        except Exception:  # noqa: BLE001
            pass

    task.add_done_callback(_done)


# ── contrato WEB restaurado (demo 2026-07-14: the search corrio INVISIBLE) ────────────────────────────────
# En the refactor V2-038 (P2) the flujo `kind=web` is unifico bajo the WorkerSession generico and is PERDIÓ the step
# of `web_cc` that creaba the task+TARJETA of the browser and daba al worker the contrato of cierre → the worker of the
# demo navego 12+ min without superficie visible ni entrega. Se restaura AQUÍ, inside of the sustrato new:
# a task = a tab = a tarjeta (continuidad V2-032 incluida) + prompt web with criterion of CIERRE.
_FORCE_NEW_RE = _d.re.compile(
    r"\b(otro|otra|segundo|segunda|nuevo|nueva|aparte|adem[aá]s|en paralelo|a la vez)\b[^.]*"
    r"\b(navegador|pesta[ñn]a|ventana|b[uú]squeda|tarea)\b", _d.re.I)
_COEXIST_RE = _d.re.compile(r"\bsin (parar|detener|cerrar|tocar)\b", _d.re.I)


async def _prepare_web(rec: "_d.SessionRecord", req: str, reuse_tid: str = "") -> str:
    """kind=web: crea (or RE-USA, continuidad V2-032/V2-049) the task of the browser and ABRE su tarjeta ANTES of
    start the worker. Devuelve the id of navtask ('' if the subsistema no esta). El id viaja al worker by
    ZAELAR_NAV_TASK → sus capturas/actions casan with ESTA tarjeta (and su tab, that persiste in the owner)."""
    try:
        from widgets.navegador import tasks as navtasks
    except Exception:
        return ""
    try:
        # V2-049: reanudacion EXPLÍCITA → same tab that alcanzo the worker anterior (continues in su pagina).
        cont = None
        if reuse_tid and navtasks.get(reuse_tid):
            cont = (reuse_tid,)
        force_new = bool(_d._FORCE_NEW_RE.search(req)) or bool(_d._COEXIST_RE.search(req))
        if cont is None and not force_new:
            try:
                cont = navtasks.find_continuation(req)
            except Exception:
                cont = None
        # ONE TAB, ONE DRIVER (measured live 2026-08-21, `search-secondhand-monitor`). Three workers on the same
        # errand were each handed nav task `t6`, and they drove it at once: 46, 27 and 7 actions interleaved on one
        # page. The damage is not cosmetic — element refs are HANDED OUT PER LOOK (V2-248), so `click [29]` from the
        # second worker landed on whatever the first had just turned the page into. On a checkout page that is not a
        # dirty result, it is the wrong ACTION.
        #
        # The cause is two similarity judgements about the SAME pair of texts disagreeing: `find_duplicate` (Jaccard
        # >= 0.60 on content words) said "different errands" and spawned three workers, while `find_continuation`
        # (>= 2 shared stemmed subjects OR Jaccard >= 0.40) said "same browsing session" and gave them one tab. Both
        # predicates are defensible on their own; what is never defensible is the combination, so the contradiction
        # is resolved HERE, where it becomes physical. Continuation stays available for the case it was written for
        # — the operator refining a task whose worker is gone — and stops being a way to share a live tab.
        if cont:
            _held = _d.record_by_nav_task(str(cont[0]))
            if _held is not None and _held is not rec and _held.status in _d.LIVE_SESSION_STATES:
                _d.logger.warning(f"dispatch: la pestaña {cont[0]} ya la conduce {_held.task_id} → pestaña nueva")
                cont = None
        if cont:
            tid = str(cont[0])
            try:
                navtasks.set_goal(tid, req)
                # V2-571: a reused tab now serves THIS errand, so its sheet stamp follows it — a stale stamp
                # routes findings and refreshes to the predecessor's box (the V2-434 «sello rancio»).
                navtasks.set_sheet(tid, _d.sheet_of(rec))
            except Exception:
                pass
        else:
            _tr = str(getattr(rec, "trace_id", "") or "")   # V2-281: la HOJA viaja con la pestaña, como el trace
            tid = str(navtasks.create(req, trace=_tr, sheet=_d.sheet_of(rec)))
        # V2-571 — ONE widget per errand: with a sheet, its PROCESS tab embeds the browser (`sheet_browser`)
        # and the separate monitor card is NOT opened. A sheetless task keeps its card — only surface it has.
        if not _d.sheet_of(rec):
            try:
                from voice.observer import emit
                emit("widget", "show", extra={"id": navtasks.inst_id(tid), "src": f"worker:{tid}"})
            except Exception:
                pass
        try:
            navtasks.set_status(tid, "working")
            navtasks.set_phase(tid, "conduciendo el navegador", True)
        except Exception:
            pass
        try:  # esencia del objetivo en la cabecera de la tarjeta (sintetizador existente; best-effort)
            from nucleo.agentes.web import _synthesize_goal
            s = await _synthesize_goal(req)
            if s:
                navtasks.set_goal_summary(tid, s)
        except Exception:
            pass
        rec.nav_task = tid
        return tid
    except Exception as e:  # noqa: BLE001
        _d.logger.warning(f"dispatch: _prepare_web falló (la tarea corre sin tarjeta): {e}")
        return ""


async def _finalize_web(rec: "_d.SessionRecord", keep_open: bool = False) -> None:
    """Cierra the TARJETA of the browser with it encontrado: extrae the anuncios that quedaron in pantalla (the
    tab of the owner continues live although the worker haya dead/sido matado) and fija the state final. Best-effort.
    V2-049: if `keep_open` (operation web incompleta that is va a REANUDAR), NO the marca «failed» — the leaves in PAUSA
    (working) for that the tab and su pagina is conserven and the worker reanudado continue donde estaba."""
    tid = getattr(rec, "nav_task", "")
    if not tid:
        return
    items: list = []
    try:
        from widgets.navegador import tasks as navtasks
        try:
            from widgets.navegador import owner
            tb = owner._task_browsers.get(str(tid))
            if tb is not None:
                items = await tb.extract_listings()
                if items:
                    navtasks.set_results(tid, {"conclusion": (rec.result_summary or "").strip()[:300],
                                               "items": items[:5]})
        except Exception:
            pass
        if rec.status == "cancelled":
            navtasks.cancel(tid)
        elif keep_open:
            navtasks.set_phase(tid, "en pausa — reanudando la gestión", True)     # pestaña VIVA para el resume
        else:
            navtasks.finish(tid, "done" if rec.ok else "failed",
                            ("✅ " if rec.ok else "") + ((rec.result_summary or "").strip()[:200]
                                                        or "sin resultado"))
        # V2-257 — tercer and ultimo camino by the that the browser encuentra something; the three pasan already by the same
        # puerta (`widgets/results/intake`). Va DESPUÉS of the cierre by two razones: mantiene pegados the
        # `set_results` and the final that exige the invariante of V2-192 (a task VIVA no can tener results),
        # and leaves outside the caso `cancelled` — the operator said that parasemos, so that no le llenamos the sheet.
        if items and rec.status != "cancelled":
            try:
                from widgets.results import intake as _intake
                _intake.push(items, sheet=_d.sheet_of(rec),
                             source_url=str((navtasks.get(tid) or {}).get("url") or ""))
            except Exception:  # noqa: BLE001
                pass
            # …and the HECHO a the conversacion. Escribir the filas and no contarlo es it that media the arnes the
            # 2026-08-24: llegaban a the sheet 42-113 s before of the ultimo turn and the agent seguia diciendo
            # «still no tengo nothing». `intake.push` no lleva nota a purpose —es the puerta shared of the
            # three caminos and the nota the empuja the caller— and of the three este era the only that no the empujaba.
            # La condicion of «only if nadie it ha contado already» lives with the resto in `workers/findings.py`.
            try:
                from nucleo.workers import findings as _find
                _find.hand_sheet_finding(tid, items, rec.goal)
            except Exception:  # noqa: BLE001
                pass
    except Exception:
        pass


async def _compose_context(request: str, kind: str) -> str:
    """Contexto minimo of memory for the worker (best-effort, off-voice). Fail-open a empty, but AVISANDO:
    the fail-open silencioso escondio durante todo V2-038 a typo (`compose_task_context`, funcion inexistente)
    that dejaba a TODOS the workers without the bloque «CONTEXTO DE MEMORIA» (auditoria 2026-07-14)."""
    try:
        from nucleo import memory_agent
        return await memory_agent.compose_context(request, budget=2000)
    except Exception as e:  # noqa: BLE001
        _d.logger.warning(f"dispatch: compose_context falló ({e}); el worker {kind} sale SIN contexto de memoria")
        return ""
