"""El bloque de TAREAS DE FONDO EN CURSO — lo que los Brain Workers están resolviendo AHORA.

Extraído de `live_blocks` el 2026-08-28 por el trinquete de arquitectura, con el mismo criterio y el mismo
precedente que `navegador_lines` (V2-276) y `errand_sheet` (V2-432): se compone ENTERO a partir de un solo
registro —`dispatch.pending_summaries()`— y no comparte un dato con los otros bloques. Mudanza, no cambio de
interfaz; el contrato público sigue siendo `prompt.live_state()`, y `live_blocks` lo re-exporta.

Las CARAS y el porqué de cada una siguen documentados donde se aplican: sin paso reportado (V2-133) ·
encallada (V2-131) · sin avanzar un paso del plan (V2-354) · lo que el worker DICE haber encontrado (V2-444) ·
algo ya entregado con la tarea viva (V2-222) · algo ha FALLADO (V2-348) · las filas de su hoja (V2-451) · y la
oferta de parar, que se hace UNA vez (V2-454).
"""
from __future__ import annotations

from nucleo.flash.errand_sheet import rows_of_sheet

def _short_note(note: str, limit: int = 110) -> str:
    """A worker's step note, shortened WITHOUT cutting a word in half — and saying so when it was cut.

    Measured 2026-08-23 (`cheapest-monitor`, round 7): a hard `[:60]` turned

        «Comparativa entregada en pantalla (hoja de resultados con los 3 finalistas)»

    into «…con lo», dropping exactly the words that said results existed. The brain, asked four times
    whether it had anything, answered «sigo pendiente» over a sheet already holding three candidates.

    Two rules, and the second matters as much as the first: cut on whitespace, and mark the cut with an
    ellipsis. A truncated note that ends cleanly reads as a COMPLETE one, which is how «con lo» became a
    sentence the model was entitled to treat as the whole message.
    """
    n = " ".join((note or "").split())
    if len(n) <= limit:
        return n
    head = n[:limit]
    cut = head.rfind(" ")
    return (head[:cut] if cut > limit // 2 else head).rstrip(" ,;:.") + "…"


def pending_task_lines() -> list[str]:
    """El bloque de TAREAS DE FONDO EN CURSO, renderizado (V2-348).

    Mudado desde `prompt.live_state()` el 2026-08-26 por el trinquete de arquitectura, con el mismo criterio y
    el mismo precedente que `navegador_lines()` (V2-276): es un bloque que se compone ENTERO a partir de un solo
    registro —`dispatch.pending_summaries()`— y no comparte un dato con los otros dos. Mudanza, no cambio de
    interfaz; el contrato público sigue siendo `live_state()`.

    Las CARAS y el porqué de cada una siguen documentados donde se aplican, abajo: sin paso reportado (V2-133) ·
    encallada (V2-131) · ya ha encontrado candidatos (V2-222) · algo ya entregado con la tarea viva (V2-222,
    segunda cara) · algo ha FALLADO (V2-348, la simétrica de la anterior).
    """
    lines: list[str] = []
    try:
        # V2-038 §v3·G: UNA sola verdad — el registro RAM de dispatch (no el summary_line del escalate legacy).
        # Lectura de dict en RAM (µs, sin I/O): más fresca que el bloque BRAIN WORKERS del ESTADO (proyección ~1 Hz),
        # útil para el turno inmediatamente posterior a lanzar una tarea.
        from nucleo import dispatch as _disp
        _pend = _disp.pending_summaries()
        if _pend:
            # Incluye el PASO concreto (phase) + el tiempo → el operador preguntó "¿en qué punto estás?" y recibía
            # siempre "sigue en desarrollo continuo" ("eso has dicho hace 6 min", sesión 2026-07-15). El modelo debe
            # dar el paso real + elapsed y ser HONESTO si lleva mucho en el mismo paso.
            bits = []
            _ofrecer: list[str] = []
            for t in _pend:
                ph = (t.get("phase") or "").strip()
                bit = f'«{(t.get("request") or "")[:60]}»' + (f' — {ph}' if ph else "")
                # V2-059: progreso ESTRUCTURADO si el worker lo reporta (paso N/total, %, nota) → respuesta precisa
                # a "¿cómo va?" en vez de una fase vaga.
                pct, done, total = t.get("pct", -1), t.get("done", 0), t.get("total", 0)
                if total:
                    bit += f' [paso {min(done, total)}/{total}'
                    bit += (f', {pct}%]' if pct >= 0 else ']')
                elif pct >= 0:
                    bit += f' [{pct}%]'
                if t.get("note"):
                    # 60 chars used to CUT THE PAYLOAD OUT of the note, and measured 2026-08-23 on
                    # `cheapest-monitor` (round 7) that cost the round. The worker reported
                    #     «Comparativa entregada en pantalla (hoja de resultados con los 3 finalistas)»
                    # and the prompt carried
                    #     «Comparativa entregada en pantalla (hoja de resultados con lo»
                    # — severed mid-word at exactly the point where it said results EXIST and how many. The
                    # brain then spent five turns answering «sigo pendiente» over a sheet that already held
                    # Dell, LG and MSI. A note is written to be read whole; cut it on a WORD boundary and say
                    # out loud when it was cut, so a truncated note can never read as a complete one.
                    bit += f' — {_short_note(str(t["note"]))}'
                if not ph and pct < 0 and not total and not t.get("note"):
                    # SIN PASO REPORTADO. Se dice con esas letras (V2-133): el bloque pedía «di el PASO concreto»
                    # a secas, y cuando no había ninguno el modelo rellenaba el hueco NARRANDO uno. La tanda del
                    # 2026-08-18 lo midió en 8 de 12 casos, con la forma exacta de una fase de worker: «en estos
                    # momentos está en la fase de login» de un gimnasio cuyo nombre todavía no tenía. No es que
                    # el modelo mintiera por gusto: se le mandaba decir algo que nadie le había dado.
                    bit += " — SIN paso reportado aún"
                # V2-131 — «llevo un rato intentándolo y parece que se está demorando» dicho al ARRANCAR, y
                # después seis turnos de «sigue en marcha» sobre una tarea que no había emitido nada. El
                # supervisor de `nucleo/loop.py` SÍ sabía que estaba encallada (`silent_s`, umbral compartido)
                # y lo decía por su cuenta; aquí nunca llegaba, así que el cerebro solo veía «arrancó hace N
                # segundos» y tenía que adivinar qué cuenta como mucho. Se le da el HECHO, como con «SIN paso
                # reportado aún»: la instrucción vaga («si lleva MUCHO, sé honesto») pedía un juicio con el
                # dato fuera de la vista.
                _silent = int(t.get("silent_s", 0) or 0)
                _atascada = False
                if _silent >= _disp.STUCK_SECS:
                    bit += f" — ENCALLADA: {_silent // 60} min SIN DAR NINGUNA SEÑAL"
                    _atascada = True
                # V2-354, TERCERA cara de la misma familia: viva, hablando, y sin avanzar UN paso de su plan.
                # Medido en `restaurant-tonight-madrid` (2026-08-27): plan de 4 pasos declarado a los 49 s y el
                # primero reportado a los 380 — **331 segundos en «0/4, 0%»** mientras navegaba y leía capturas.
                # Ninguna cara salió: ENCALLADA mira el SILENCIO y ésta no callaba; «SIN paso reportado» no
                # aplica porque plan SÍ había. Y el plan lo empeora en vez de ayudar — «0/4, 0%» se lee como
                # «no ha empezado», que es una cifra tranquilizadora, y el operador tuvo que insistir tres
                # veces. Va en un `elif`: una tarea CALLADA ya está dicha, y decir las dos es ruido.
                elif int(t.get("total", 0) or 0) and int(t.get("no_step_s", 0) or 0) >= _disp.NO_STEP_SECS:
                    _ns = int(t["no_step_s"])
                    bit += (f" — SIN AVANZAR: {_ns // 60} min sin completar un paso "
                            f"(sigue en {min(int(t.get('done', 0) or 0), int(t['total']))}/{int(t['total'])})")
                    _atascada = True
                # V2-454 — LA OFERTA DE PARAR SE HACE UNA VEZ. El hecho se queda (V2-224).
                if _atascada:
                    if _disp.stall_offered(t.get("id")):
                        bit += " [YA le ofreciste pararla: NO se lo vuelvas a preguntar]"
                    else:
                        _ofrecer.append(str(t.get("id") or ""))
                # V2-222, third face — measured on `search-secondhand-monitor__es` (2026-08-23 23:24). The
                # browser block said, in the same prompt, «YA TIENE RESULTADOS … DÁSELOS en este turno», and
                # this one said «en cola (llevas 23s)». Two registries describing ONE errand, disagreeing:
                # the finalists live in the worker record (`kept`, written by `hbnote considered --kept N`),
                # and this block never read it, so the queue phase — which the worker had simply never
                # updated — was the only thing here. The turn answered «te aviso en cuanto tenga
                # resultados» with 35 real listings on the sheet, twice, and the round was scored as
                # disobedience. It was not: a self-contradicting prompt has no obedient answer. The datum
                # is already on the summary; the same signal the browser face reads (V2-200) is read here.
                _kept = int(t.get("kept", 0) or 0)
                if _kept > 0:
                    bit += f" — DICE haber encontrado {_kept} candidato(s)"   # V2-444: SU cuenta, sin comprobar
                _f = rows_of_sheet(str(t.get("sheet") or ""), 3) if t.get("sheet") else []   # V2-451
                if _f:
                    bit += " — YA ENTREGADO (de su hoja): " + "; ".join(_f)
                bits.append(bit + f' (llevas {t.get("secs", 0)}s)')
            for _t in _ofrecer:
                _disp.mark_stall_offered([_t])     # V2-454: este turno la lleva delante
            lines.append("TAREAS DE FONDO EN CURSO (los brain workers las están resolviendo; NO reinicies ni digas "
                         "que ya está): " + "; ".join(bits) + ". Si el operador pregunta el estado, di el PASO "
                         "concreto y el tiempo que lleva; si lleva MUCHO en el mismo paso, sé honesto (va lento o "
                         "puede haberse atascado, le ofreces pararlo) — NUNCA repitas la misma frase vaga. "
                         "Lo que ves AQUÍ es TODO lo que sabes de esas tareas: si una sale «SIN paso reportado "
                         "aún», di exactamente eso —que arrancó y todavía no ha dado señal—; JAMÁS te inventes en "
                         "qué punto va («está en la fase de login», «la farmacia está consultando tu historial», "
                         "«ya tengo la reserva en marcha»). Inventar un paso es MENTIR sobre lo único que el "
                         "operador no puede comprobar por su cuenta, y se nota tarde y mal. "
                         # V2-131 — lo que hay que hacer con el hecho, no solo el hecho.
                         "Los SEGUNDOS que ves son la verdad: no digas que algo «se está demorando» ni «lleva "
                         "un rato» si acaba de arrancar. Y si una tarea sale ENCALLADA o SIN AVANZAR, dilo con "
                         "esas letras y ofrece pararla, salvo que ponga que YA se lo ofreciste: entonces el "
                         "hecho se dice igual —sigue sin avanzar y desde cuándo— pero la pregunta NO se "
                         "repite, porque ya te contestó. NO respondas "
                         "«sigue en marcha» otra vez; «sin avanzar» NO es «no ha empezado»: está trabajando y "
                         "no llega, y el operador merece decidir si espera. Si el operador te pide un resultado CONCRETO (¿hay o no hay?, ¿cuánto "
                         "cuesta?, ¿está reservado?) y la tarea no lo ha traído, la respuesta es que TODAVÍA NO "
                         "LO SABES y desde cuándo lleva sin dar señal — nunca una vuelta más de proceso. "
                         # V2-222 again, and the same lesson as `recently_ended_sessions`: the block had a
                         # prohibition («NO … digas que ya está») and an instruction for the empty case
                         # («TODAVÍA NO LO SABES»), and NOTHING for the case in between — a step note saying
                         # something already landed while the errand keeps running. With no branch licensing
                         # it, the model resolved the collision the only way the block allowed and denied a
                         # delivery that was on screen. The fork goes INSIDE the imperative rather than in a
                         # separate sentence: two orders in one paragraph come out heads-or-tails.
                         "PERO lee el PASO antes de decir eso: si dice que algo ya está ENTREGADO, ESCRITO o "
                         "EN PANTALLA, entonces la tarea SÍ ha traído eso — cuéntalo en este turno, di qué hay y qué"
                         " falta todavía, y NO contestes «sigo con ello». Un «DICE haber encontrado N» es SU cuenta sin"
                         " comprobar: puedes decir que va sacando cosas y que aún no ha llegado nada que darle, pero NO"
                         " lo cuentes como entrega ni nombres nada. Lo que sigue EN CURSO es "
                         "la tarea, no lo que ya está entregado; negar una entrega que el operador tiene "
                         "delante en la pantalla es peor que no haberla hecho. "
                         # V2-348, cuarta cara y la SIMÉTRICA: solo las buenas noticias llevaban un «cuéntalo»,
                         # así que el modelo relataba la mitad que el bloque nombraba. Medido en su iniciativa.
                         "Y LO MISMO AL REVÉS, que es este mismo defecto con el signo cambiado: si el paso dice "
                         "que algo ha FALLADO —un sitio caído, un filtro que no se aplicó, un plan B— cuéntalo "
                         "TAMBIÉN en este turno, con el nombre de lo que falló y qué haces en su lugar; un "
                         "contratiempo NO se resume en «va dando pasos». Tapar una mala noticia cuesta la "
                         "confianza igual que negar una entrega, y es el operador quien decide si esperar o "
                         "cambiar de enfoque. "
                         # V2-130 — the list had no stated SCOPE, and a list in context becomes an answer
                         # when the model has a hole. Asked which barber he always goes to, the brain had
                         # nothing on barbers and offered these instead: «tengo varias tareas tuyas
                         # pendientes: reservar mesa en Casa Lucio, renovar la cuota del gimnasio…».
                         # Real items, real list — wrong KIND of thing. Naming what the list is NOT costs
                         # one clause and closes the substitution.
                         "Y esto es una lista de TRABAJO EN CURSO, no un registro de sus sitios, sus "
                         "contactos ni sus costumbres: si te pregunta cuál es su peluquería, su médico o "
                         "«el de siempre», estas tareas NO son candidatas — no se las ofrezcas. "
                         # V2-142 — turno 1, con una tarea de OTRA petición todavía viva: «Tienes dos cosas:
                         # primero necesito los datos del recibo de la luz para preparar la transferencia, y
                         # segundo voy a pedir la reposición de tu receta». El operador solo había hablado de
                         # la receta. El bloque decía qué HACER con la lista y (desde V2-130) una cosa que la
                         # lista NO es; faltaba la que de verdad mordió: que no es parte de lo que te piden
                         # ahora. Un modelo pequeño con una lista delante y una petición nueva las suma.
                         "Y NO forman parte de lo que te pide AHORA: si te encarga algo nuevo, atiende ESO "
                         "solo — no lo mezcles con una tarea vieja («tienes dos cosas: primero el recibo de la "
                         "luz y segundo tu receta») ni le pidas datos que hacen falta para la otra.")
    except Exception:
        pass
    return lines
