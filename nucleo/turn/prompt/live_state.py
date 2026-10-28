"""What is true THIS second, read once per turn — the volatile tail of the prompt (refactor2710-08 T-02).

One reader per truth: the screen (`state.open_widgets`, the canvas's own report), the clock, the errands and the record
(`live_blocks`), the confirmations, the search health, the dropped calls, the finished sessions.
"""
from __future__ import annotations

from files import attachments as _attachments
from nucleo.flash import live_blocks as _live_blocks
from voice import screens as _screens


def _open_widget_ids() -> set[str]:
    """IDs of widgets OPEN now, from STATE (µs read, one SELECT—does not touch the retriever, honoring V2-011).
    The resource layer uses them to include items/coaching ONLY for what is in front of the operator."""
    try:
        from memory import api as memory
        return {str(w).strip().lower() for w in (memory.state().get("open_widgets") or []) if str(w).strip()}
    except Exception:
        return set()


def screen_line() -> str:
    """The screen, read ONCE per turn from the canvas's report (`state.open_widgets`); empty says so (2026-09-19)."""
    ids = [str(w).strip() for w in (__import__("memory.api", fromlist=["x"]).state().get("open_widgets") or [])]
    return "En pantalla: " + (", ".join([i for i in ids if i][:12]) or "nada (pantalla VACÍA)") + "."


def _recent_widget_ids() -> list[str]:
    """IDs of RECENTLY USED widgets (MRU `state.recent_widgets`, V2-078), in recency order. Second narrowing
    layer for selecting/resolving the target widget (open > recent > catalog). µs read, no retriever."""
    try:
        from memory import api as memory
        return [str(w).strip().lower() for w in (memory.state().get("recent_widgets") or []) if str(w).strip()]
    except Exception:
        return []


def live_state() -> str:
    """Cheap, tool-free reads that FlashBrain answers instantly."""
    import time as _t
    # EXPLICIT dates (today, tomorrow) so the model never searches or invents one (V2-026: it once web-searched it).
    _tm = _t.strftime("%Y-%m-%d", _t.localtime(_t.time() + 86400))
    lines = [f"Hora local: {_t.strftime('%H:%M')} · hoy es {_t.strftime('%A %d %b')} ({_t.strftime('%Y-%m-%d')}); "
             f"mañana es {_tm}."]
    # NEXT 7 DAYS with dates (V2-121): scheduling "Wednesday" needs WHICH date, and mental date arithmetic is where a
    # small model silently errs — a misdated reminder only shows when it fails to fire. With this list, the absolute
    # date `[[cron.create]]` needs is a LOOKUP. ~90 chars/turn; computed without I/O.
    _now = _t.time()
    _days = "; ".join(f"{_t.strftime('%A', _t.localtime(_now + i * 86400)).lower()} "
                      f"{_t.strftime('%Y-%m-%d', _t.localtime(_now + i * 86400))}" for i in range(1, 8))
    # V2-473 (round 4): the list TRANSLATES named days, but without that explanation the model treated it as the
    # calendar limit—"my upcoming-days list only reaches the 5th"—rejecting a valid appointment ten days away
    # and then asking "is it 2026?".
    lines.append(f"Próximos días (para traducir un día NOMBRADO —«el miércoles»— a su fecha): {_days}. "
                 "NO es el límite de tu agenda: una fecha explícita («el 8 de septiembre») se apunta tal "
                 "cual, a cualquier distancia, y sin año es del año en curso (o del siguiente si ya pasó) "
                 "— no pidas confirmación de ninguna de las dos cosas.")
    lines.append(screen_line())
    # V2-348 — TAREAS DE FONDO live in `live_blocks.py` (V2-276 precedent); V2-799 — what is pending or stopped.
    lines.extend(_live_blocks.pending_task_lines() + _live_blocks.pending_work_lines())
    lines.extend(_live_blocks.recent_lines() + _live_blocks.earlier_lines())   # the record: lately, then the days before
    lines.extend(_live_blocks.navegador_lines())
    lines.extend(_live_blocks.harness_lines())   # V2-660: an open harness goal is a FACT with its rule
    lines.extend(_live_blocks.done_ops_lines())  # V2-707 F6: and so is a mutation that already RAN
    lines.extend(_live_blocks.shelf_lines())     # V2-773: a finished errand's closed sheet has a name
    try:
        # AUSENCIA de ubicación, dicha con todas las letras (V2-127). Sin esto el prompt manda usar «la ciudad
        # del operador» y no hay ninguna: el hueco se rellena con una plausible y el operador oye el nombre de
        # una ciudad que él no ha dicho. Mismo remedio que la marca «SIN paso reportado aún»: nombrar el hueco.
        # Coste CERO cuando el estado sí la trae — la línea ni aparece.
        from memory import api as _memapi_loc
        _mstate = _memapi_loc.state() or {}
        if not _mstate.get("location"):
            lines.append("NO SABES dónde vive el operador (su ESTADO no tiene ubicación): no supongas ninguna "
                         "ciudad ni la nombres; si hace falta para lo que te pide, pregúntasela.")
    except Exception:
        _mstate = {}
    # WAKE WORD MODE is a fact the model must HOLD, not guess (2026-09-09, session 8a07e8d9: it invented it knew
    # neither name and never called the tool). Runtime config, so it lives here and not in the stable prefix.
    # Runtime-mode lines riding the set_style_directive tool (wake-word mode + V2-633 silent-orders):
    # composed in `nucleo/flash/style_directive.py`, the module that also HANDLES that tool (extracted
    # paying the ratchet — the teaching and the handler stay in one place).
    try:
        from nucleo.flash import style_directive as _styled
        lines.extend(_styled.prompt_lines(_mstate))
    except Exception:
        pass
    lines.extend([*filter(None, [_screens.slot_line()]), *_attachments.prompt_lines()])  # V2-792 · V2-809 attached
    try:
        from widgets import confirm as _confirm
        cl = _confirm.pending_line()
        if cl:
            lines.append(cl)
    except Exception:
        pass
    # V2-176 — LA CAPA DE BÚSQUEDA ESTÁ CAÍDA, y sin esto no había forma de decirlo. Un resultado vacío es
    # indistinguible de «busqué y no hay nada», así que el turno decía lo único que tenía: «sigo con ello».
    # Medido en `cheapest-monitor`: veinte eventos de búsqueda, cero candidatos, diez turnos de «te aviso en
    # cuanto lo tenga» y un `stuck/nudge` del watchdog mientras ocurría. La cadena estaba abajo (cuota agotada y
    # un CAPTCHA), o sea que el RESULTADO no era alcanzable — y lo único que sí lo era, decirlo, tampoco, porque
    # nada llevaba el hecho hasta aquí.
    #
    # Se dice el MOTIVO, no un genérico: «se me ha agotado la cuota» y «me están pidiendo un captcha» llevan al
    # operador a decisiones distintas, y ninguna de las dos es esperar.
    try:
        from nucleo import websearch as _ws_health
        _sf = _ws_health.recent_failure()
        if _sf:
            _why = {"quota": "se ha agotado la cuota de búsqueda",
                    "captcha": "el buscador está pidiendo verificación anti-robot",
                    "credential": "falta o no vale la credencial del buscador",
                    "network": "no hay salida a la red para buscar"}.get(str(_sf.get("kind")),
                                                                         "la búsqueda está fallando")
            lines.append(
                f"TUS BÚSQUEDAS WEB NO ESTÁN FUNCIONANDO ({_why}): no es que el mundo no tenga lo que busca — es "
                f"que no puedes mirar. Si el operador espera un resultado de una búsqueda, DÍSELO con esas "
                f"letras en vez de pedirle que siga esperando, y ofrécele lo que sí puedes hacer (mirar una web "
                f"concreta con el navegador, o que te dé él un sitio por donde empezar). Prometer que avisarás "
                f"«en cuanto lo tenga» es prometer algo que no va a llegar.")
    except Exception:
        pass
    # V2-176 frente 2 — una ACCIÓN que el sistema tiró. V2-171 la registró en las métricas del turno y en
    # observabilidad; el turno SIGUIENTE no veía nada, así que la conversación continuaba como si hubiera
    # salido. La frase («te pongo con ello») ya se dijo; lo que todavía se puede arreglar es el turno de
    # después. Es el mismo remedio que `recently_finished()` y que la confirmación caducada: un hecho que solo
    # vive un turno es un hecho que la conversación pierde.
    try:
        from nucleo.llm import fast_client as _fc_drop
        _drops = _fc_drop.recent_drops()
        if _drops:
            _names = ", ".join(sorted({str(d.get("name") or "?") for d in _drops}))
            lines.append(
                f"UNA ACCIÓN TUYA NO LLEGÓ A EJECUTARSE ({_names}): el sistema no pudo leerla y la descartó, "
                f"así que lo que dijeras que ibas a hacer con ella NO ha pasado y no va a pasar solo. Dilo con "
                f"esas letras si viene a cuento y vuelve a intentarlo — no sigas hablando como si hubiera "
                f"salido.")
            _fc_drop.clear_drops()
    except Exception:
        pass
    # V2-570 — una ENTREGA de la pasada rápida de anuncios también es un hecho, y viaja CON su instrucción
    # (la lección de V2-453: el hecho sin la orden no cambia nada). Medido en la sesión 9dcff6f5 (catamaranes):
    # el modelo tenía las filas entregadas delante y escaló la MISMA caza a un worker — la única instrucción
    # junto a ellas cubría «si te pide el enlace». Esta línea nombra la regla lineal del operador; el cinturón
    # determinista vive en `nucleo/request/append.py` para cuando el modelo la desobedece igualmente.
    try:
        import time as _t_ls
        from nucleo.workers import ended as _end_ls
        _dels = _end_ls.recent_listing_deliveries()
        if _dels:
            _d0 = max(_dels, key=lambda r: float(r.get("at") or 0))
            _ago = max(0, int(_t_ls.time() - float(_d0.get("at") or _t_ls.time())))
            lines.append(
                f"BÚSQUEDA DE ANUNCIOS YA HECHA (hace {_ago}s): «{(_d0.get('goal') or '')[:70]}» → "
                f"{int(_d0.get('n') or 0)} resultados YA en su hoja, en pantalla. Si pide AFINAR o más "
                "(otro tamaño, otra zona, precio), llama a search_listings OTRA VEZ con todos los filtros "
                "acumulados — NUNCA escalate_to_slowbrain para la misma caza: si hace falta ir a fondo, el "
                "sistema lo lanza solo.")
    except Exception:
        pass
    # V2-198 — una SESIÓN de worker que acabó también es un hecho. `pending_summaries()` solo trae las vivas,
    # así que al terminar desaparecía del estado sin dejar rastro y el turno se quedaba con su propia memoria de
    # haberla arrancado. Es lo que V2-150 cerró para las tareas de navegador… un nivel por encima, y peor: una
    # tarea de navegador solo existe con `kind=web`, mientras que TODA escalada abre una sesión de worker.
    try:
        from nucleo import dispatch as _disp_end
        _ended = _disp_end.recently_ended_sessions()
        if _ended:
            _eb, _failed, _failed_ids, _told = [], "", [], 0
            for _e in _ended:
                _st = str(_e.get("status") or "")
                _w = f"«{(_e.get('goal') or 'tarea')[:60]}»"
                if _st == "cancelled":
                    _w += " se PARÓ (cancelada)"
                elif _st == "error" or not _e.get("ok"):
                    _w += " FALLÓ"
                    if not _failed:
                        _failed = f"«{(_e.get('goal') or 'la tarea')[:50]}»"
                        _told = int(_e.get("told") or 0)
                    _failed_ids.append(str(_e.get("id") or ""))
                else:
                    _w += " TERMINÓ"
                if _e.get("summary"):
                    _w += f" — {_e['summary'][:110]}"
                _eb.append(_w)
            _head_end = "TAREAS DE FONDO — YA ACABADAS: " + "; ".join(_eb) + "."
            if _failed:
                # V2-221 — la instrucción de V2-198 era CONDICIONAL («si el operador pregunta por ello») y una
                # tarea MUERTA no es una pregunta pendiente: es una espera que no se va a resolver sola. Medido
                # por el arnés en `hotel-under-15-days` (19:12) leyendo el prompt de cada turno: **ocho turnos
                # consecutivos** con «… FALLÓ» delante contestando «sigo con ello, te aviso», sin muro y sin
                # pregunta de por medio. O sea que la ENTREGA ya estaba (V2-198 pone el hecho en el prompt) y lo
                # que falla es la OBEDIENCIA — exactamente el mismo corte que V2-185 hizo con el muro: mientras
                # la mitad tranquilizadora sea la que dice qué hacer, el modelo cree a esa.
                # V2-224 — y si YA se lo dijiste, la cara cambia entera. La cláusula «si ya se lo dijiste no lo
                # repitas» iba DENTRO de esta misma frase imperativa, y el arnés la midió en dos rondas del mismo
                # commit con resultados opuestos: en una repitió el aviso cinco turnos seguidos (V2-189 otra vez),
                # en la otra se calló ENTERO y volvió a «sigo con ello» siete turnos. Pedirle al modelo que
                # dedujera de la ventana si ya lo había dicho era pedirle un hecho que nosotros teníamos y no le
                # dábamos. Ahora se cuenta (`dispatch.mark_death_reported`) y la instrucción es una sola cosa por
                # turno. Y la redacción sigue la frase con la que el arnés lo diagnosticó: **callar la repetición
                # no es callar el estado**.
                if _told:
                    lines.append(
                        _head_end + f" YA le dijiste que {_failed} no acabó bien, así que NO se lo vuelvas a "
                        "anunciar: repetirlo es el disco rayado. Pero SIGUE MUERTA. Si pregunta cómo va, si dice "
                        "que espera tranquilo o si te da las gracias por seguir con ello, NO digas «sigo con "
                        "ello» ni «te aviso en cuanto lo tenga» ni «dame un momento»: eso contradice lo que ya "
                        "le dijiste. Di en una frase dónde está la cosa de verdad —esa murió, y qué has hecho o "
                        "puedes hacer desde entonces— y sigue con lo que él quiera ahora.")
                else:
                    lines.append(
                        _head_end + f" {_failed} NO ACABÓ BIEN y el operador NO LO SABE: está esperando un "
                        "resultado que ya no va a llegar. DÍSELO EN ESTE TURNO, aunque no pregunte y aunque "
                        "acabe de decir que espera tranquilo —esperar es justo lo que hará si te callas—, y con "
                        "una salida concreta: reintentarlo, probar otra vía, o dejarlo. NUNCA «sigo con ello» "
                        "ni «te aviso en cuanto lo tenga» encima de algo que el sistema ya da por muerto.")
                try:
                    _disp_end.mark_death_reported(_failed_ids)
                except Exception:
                    pass
            else:
                lines.append(
                    _head_end + " Eso YA NO está en marcha: si el "
                    "operador pregunta por ello, di cómo acabó y con qué —y si trajo algo, DÁSELO— en vez de "
                    "«sigo con ello», que es contar algo que el sistema da por acabado. Si acabó sin nada útil, "
                    "dilo y ofrece el siguiente paso.")
    except Exception:
        pass
    try:
        # Hermana de la de arriba, para una TAREA irreversible parada por el confirm-gate (V2-126). Sin ella el
        # cerebro no tenía forma de saber que hay algo esperando su sí: la tarea desaparece del registro al
        # pararse, así que el turno siguiente veía cero tareas y volvía a narrar trabajo inexistente.
        from nucleo import dispatch as _disp_c
        cline = _disp_c.confirm_line()
        if cline:
            lines.append(cline)
    except Exception:
        pass
    return "\n".join(lines)
