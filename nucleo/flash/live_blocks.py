"""nucleo/flash/live_blocks.py — the rendered LIVE STATE of the BROWSER (V2-276).

Extracted from `prompt.live_state()` on 2026-08-24 to pay down the architecture ratchet
(`test_architecture_ratchet`), which had been red since the previous night's commits: `prompt.py` was 56
lines above its ceiling, and that table's rule is explicit — a growing file calls for EXTRACTING a
module, never raising the number.

This fragment was chosen because the boundary already existed: it is the only one of the three `live_state()`
blocks composed ENTIRELY from the browser registry (`widgets.navegador.tasks`) and sharing no data with the
other two. Its three helpers — the stall threshold, the human-readable site name, and the “found something”
signal — have no other callers in the engine, so they travel with it.

They are re-exported from `prompt` because tests import them by name from there, and because the public
contract remains `live_state()`: this is a move, not an interface change.

The block's FACES (pending question · has results · stopped waiting for login · blocked · healthy), and the
reason for each, remain documented where they are applied below. Node 4.21
(`test_every_face_is_reachable`) walks this file, requiring that each one can actually be triggered.
"""
from __future__ import annotations

# V2-167 — how long a browser task may sit on the SAME page before the turn is allowed to call it stalled. Two
# minutes, taken from the initiative's own bar: «un "este sitio me ha bloqueado, ¿lo intento en otro?" a los dos
# minutos vale más que cinco PASS». It is a REPORTING threshold, never a kill: nothing here stops a task, and a
# marketplace that legitimately takes minutes keeps working while the operator is told what it is doing.
_STALLED_S = int(__import__("os").environ.get("ZAELAR_NAV_STALLED_S", "120") or 120)


def _found_candidates(nav_task_id: str) -> bool:
    """Has the worker driving this tab already FOUND something?

    The browser task's own `results` cannot answer this while it is alive — every caller of `set_results()`
    calls `finish()` in the next breath, so an active task with results does not exist in production (V2-200).
    What DOES exist live is the worker's own report of breadth: `kept` is how many finalists it has, written
    by `hbnote considered --kept N` while it works.

    Read through the seam that already links the two registries (`dispatch.record_by_nav_task`, V2-048) rather
    than a new one. Best-effort: not knowing means «no», which keeps the stall/wall faces exactly as they were.

    ⚠️ AND IT SAYS HOW MANY, NEVER WHERE (V2-278). `kept` is BREADTH — the worker's own count of finalists — and
    says nothing about the sheet having been written. Measured on `search-secondhand-monitor__es`
    (2026-08-24 01:47), the round that PASSED: turn 6 said «Ya tengo resultados EN PANTALLA» at 130 s and the
    first row landed at 142. Twelve seconds of a false claim about what the operator has in front of them, and
    the judge filed it [alta] as an unbacked claim — which is what it looks like from outside. The names were
    not invented: we had handed them over by note (V2-223). What was false was the PLACE, and we were the ones
    saying it — in this block's bit and in the browser face's imperative, both of which claimed the sheet off
    this signal. Same family as V2-209 («Aquí lo tienes» over an empty card) and V2-176 («Hecho.» over a task
    that had just started): one of OUR canned phrases is where a false claim slips in with nobody writing it.
    """
    try:
        from nucleo import dispatch as _d
        rec = _d.record_by_nav_task(str(nav_task_id))
        if rec and int(getattr(rec, "kept", 0) or 0) > 0:
            return True
    except Exception:
        pass
    return _sheet_has_rows(nav_task_id)


# V2-358 — un paso que el WORKER escribe sobre la PANTALLA es una afirmación suya, no un hecho nuestro.
#
# Medido en `search-buy-used-car` (2026-08-27 08:03, 1/5). A los 60,9 s el anillo de Proceso pintó, sin marca
# ninguna y junto a líneas verificadas como «9 resultados en la página»:
#
#     Preparando entrega: 10 propuestas en la hoja de resultados
#
# La hoja terminó la ronda con **0 filas**. El operador lee esa línea, mira su hoja vacía y las dos cosas no
# pueden ser verdad — y la que se cree es la que está escrita con letra de sistema.
#
# Es la misma enfermedad que V2-357 (inventar candidatos) una capa más abajo, y la misma respuesta que dio
# V2-345: **no se tira, se MARCA**. El worker AFIRMA cosas —esta casa ya pagó que una afirmación suya se
# tomara por hecho comprobado (V2-249)— y en este anillo su prosa convive con lo que sí hemos verificado, así
# que tiene que distinguirse a simple vista. Prefijar en vez de inventar un canal es el patrón del muro de
# chat.
#
# Solo se marca cuando el paso NOMBRA LA PANTALLA y la hoja está vacía: un paso mecánico («entrando en
# coches.net») no se toca, y si la hoja SÍ tiene filas la afirmación es cierta y tampoco. La lista de formas
# es corta y es de NUESTRO vocabulario —lo que el producto llama a su propia hoja—, no de un sitio de fuera:
# aquí sí sabemos exactamente cómo se nombra, que es justo lo contrario del caso de `dom.py`.
_DICE_PANTALLA = ("hoja de resultados", "en la hoja", "en pantalla", "results sheet", "on screen")


def worker_phase_is_a_claim(phase: str, sheet: str) -> bool:
    """Does this worker step assert something about the operator's sheet that the sheet does not support?

    `sheet` is the ERRAND's sheet (`sheets.sheet_of(rec)`), not a tab's: the worker writes the step about its
    OWN sheet. Without a resolved sheet the answer is NO — marking because it cannot be read would be a blind
    accusation, and this detector's silence leaves the ring exactly as it was.
    """
    p = (phase or "").strip().lower()
    if not p or not any(x in p for x in _DICE_PANTALLA):
        return False
    if not (sheet or "").strip():
        return False
    try:
        from widgets.results import data as _sheet
        items = (_sheet.view_data(sheet) or {}).get("items") or []
        return not any(str((i or {}).get("title") or "").strip() for i in items)
    except Exception:  # noqa: BLE001
        return False


from nucleo.flash.errand_sheet import _sheet_of_tab, aviso_sin_filas, boxes_of_tab, fila, rows_of_sheet


def _sheet_has_rows(nav_task_id: str) -> bool:
    """Are there already NAMED rows in this errand's sheet?

    V2-284 — la señal de arriba es un REPORTE VOLUNTARIO: solo existe si el worker se acordó de llamar a
    `hbnote considered --kept N`. Medido en la tanda del 2026-08-24 03:02, con los prompts de los diez turnos
    delante: en `search-secondhand-monitor__es` la cara NO salió ni una vez —la línea decía «en es.wallapop.com,
    1 pasos dados» y nada más— mientras el mecanismo registraba 11 navegaciones, 5 extracciones y monitores
    reales con precio y enlace. El mismo silencio en tres de los cuatro casos de la tanda, y el veredicto de los
    tres fue el mismo: «tuvo resultados reales y no los entregó». Tenía razón, y la culpa no era del turno: a su
    prompt no llegó nunca que hubiera algo.

    Las filas de la hoja son un hecho que NO depende de que nadie se acuerde: las escribe `results.intake.push`
    cuando el navegador extrae (V2-257). Y se lee por la PESTAÑA, no por el registro de sesiones vivas, porque
    es justo cuando el worker ya no está —relevado, muerto— cuando esto más falta hace (V2-281).

    Solo cuentan las filas con NOMBRE, la misma regla que la nota del navegador (V2-234): una fila sin nombre es
    un enlace que estaba en la página, no un resultado. ⚠️ Hoy ese filtro es un cinturón sobre unos tirantes —
    `results.apply_action` ya descarta la fila sin título al ENTRAR, medido— y se deja escrito porque un test
    que lo comprobara sin decirlo estaría afirmando una cobertura que tiene la capa de al lado. Su caso
    comprueba la garantía de la HOJA, así que se pone rojo el día que deje de darla.

    Best-effort: no poder leerlo significa «no», que deja las caras de atasco y muro exactamente como estaban.
    """
    try:
        from widgets.results import data as _sheet
        # TODAS las cajas del encargo, no solo la primera que resuelva: en un RELEVO el sello de la pestaña
        # apunta a la caja nueva (vacía) y los hallazgos siguen en la heredada (V2-432, ver `boxes_of_tab`).
        cajas = boxes_of_tab(nav_task_id)
        if not cajas:
            return False
        sheet, items = cajas[0], []
        for _c in cajas:
            _it = (_sheet.view_data(_c) or {}).get("items") or []
            if any(str((i or {}).get("title") or "").strip() for i in _it):
                return True
            if _c == cajas[0]:
                sheet, items = _c, _it
        # RESUELTA PERO VACÍA — y esto es lo que el aviso de V2-432 NO cubría: fallar al resolver ya se
        # cuenta, pero resolver a la caja EQUIVOCADA se ve exactamente igual que acertar. Medido el
        # 2026-08-28 en `search-buy-guitar__es`: `unresolved_errand_sheets` salió a 0 —o sea que resolvió— y
        # aun así hubo 6 turnos en los que al modelo no se le dijo que tuviera nada, con 15 candidatos en la
        # hoja. Sin esta línea, el diagnóstico se queda en «resolvió bien y algo pasa después».
        try:
            from voice.observer import emit
            emit("perf", "🧾 hoja del encargo RESUELTA PERO VACÍA", role="system",
                 extra={"nav_task": str(nav_task_id), "hoja": str(sheet), "n_items": len(items)})
        except Exception:  # noqa: BLE001 — instrumentar no puede tumbar el prompt
            pass
        return False
    except Exception as _e:  # noqa: BLE001
        # EL TERCER CAMINO MUDO, y el que quedaba. Medido el 2026-08-28 en `weekend-motor-events__es`: cuatro
        # turnos ciegos con las DOS señales a cero, o sea que ni falló al resolver ni encontró la caja vacía
        # — solo queda que esto reventara y el `except` se lo tragara. Un fallo que se traga a sí mismo es
        # peor que uno ruidoso: deja al prompt diciendo que no hay nada y a quien investiga sin nada que leer.
        try:
            from voice.observer import emit
            emit("perf", "🧾 hoja del encargo ILEGIBLE", role="system",
                 extra={"nav_task": str(nav_task_id), "error": f"{type(_e).__name__}: {_e}"[:160]})
        except Exception:  # noqa: BLE001 — instrumentar no puede tumbar el prompt
            pass
        return False


def _driver_is_gone(nav_task_id: str, prog: dict) -> bool:
    """Did this tab become DRIVERLESS? (V2-310)

    Medido el 2026-08-25 04:36: el plan de los Brain Workers agotó su límite de sesión, el worker murió al
    instante — y su pestaña siguió `working` en el registro, así que el estado decía «NAVEGADOR — YA EN CURSO»
    sobre un encargo que no conducía nadie. zaelar dijo la VERDAD («se cortó por el límite de sesión») contra
    un bloque que afirmaba lo contrario, el juez lo fichó como alucinación y la ronda salió 2/1/1/2/1. Un
    prompt que se contradice hace imposible acertar (V2-222).

    El hecho se lee de los DOS registros: la pestaña tiene SELLO DE ENCARGO (`sheet`, que solo pone
    `dispatch._prepare_web`) y no queda ninguna sesión viva conduciéndola (`record_by_nav_task`, que también
    encuentra una REANUDACIÓN automática — mientras alguien vaya a retomarla, no está huérfana).

    Conservador por diseño: una pestaña sin sello (el operador conduciendo a mano, un login) nunca es
    huérfana, un encargo sin hoja tampoco (se calla en vez de afirmar), y no poder leerlo es «no» — decir que
    un encargo murió cuando sigue vivo es peor que callarlo.
    """
    try:
        if not str((prog or {}).get("sheet") or "").strip():
            from widgets.navegador import tasks as _t
            if not str(((_t.get(str(nav_task_id)) or {}).get("sheet")) or "").strip():
                return False
        from nucleo import dispatch as _d
        return _d.record_by_nav_task(str(nav_task_id)) is None
    except Exception:  # noqa: BLE001
        return False


#: Cuánto puede ocupar el bloque de filas en el prompt. `fila()` trunca a 70 de título y 20 de dato, así que
#: una fila cabe en ~95 caracteres. MEDIDO: doce filas con los títulos al máximo ocupan **926**, o sea que a
#: doce este techo NO muerde y lleva una fila de holgura — y está bien: es el bound para que subir `n` mañana
#: no meta en el prompt lo que le dé la gana. El tope tiene que ser de TAMAÑO y no de conteo, porque una hoja
#: de títulos larguísimos con un cap por unidades no está acotada por nada.
_SHEET_ROWS_BUDGET = 1200


def _sheet_top_rows(nav_task_id: str, n: int = 12) -> list[str]:
    """The first few NAMED rows already delivered for this errand, as «title — price» strings.

    Measured on `search-buy-guitar__es` (2026-08-24, round 21): the face below ORDERS the turn to say WHAT was
    found «con nombre y precio» — and this block only ever carried the COUNT. The rows had reached the brain
    once, as a note four turns earlier, and notes do not persist; so when the operator pressed («enséñame lo
    que tengas»), the model answered «déjame mirar» over a sheet holding 27 named candidates. The judge filed
    it [alta]: «El usuario no puede elegir lo que no ve.» An instruction the prompt makes impossible to follow
    is not an instruction — it is a trap for the model AND for whoever reads the transcript.

    Same read as `_sheet_has_rows` (the sheet is durable and does not depend on anyone remembering to report);
    NAMED rows only; bounded hard, because this lands in a prompt, not on a screen. It carries WHAT the rows
    are, never WHERE they live — V2-278's boundary (never claim the screen) stays exactly where it was.
    """
    try:
        from widgets.results import data as _sheet
        # Las MISMAS cajas que mira `_sheet_has_rows`: si la señal dice que hay filas y estas líneas salen de
        # otra caja, el prompt afirma que hay algo y no puede nombrarlo — que es peor que las dos por separado.
        cajas = boxes_of_tab(nav_task_id)
        sheet = next((c for c in cajas
                      if any(str((i or {}).get("title") or "").strip()
                             for i in ((_sheet.view_data(c) or {}).get("items") or []))), "")
        if not sheet:
            aviso_sin_filas(nav_task_id, cajas)      # V2-438: el único camino que quedaba mudo
            return []
        out: list[str] = []
        _con_nombre = 0
        _chars = 0
        for i in (_sheet.view_data(sheet) or {}).get("items") or []:
            title = str((i or {}).get("title") or "").strip()
            if not title:
                continue
            if len(out) >= max(1, int(n)) or _chars >= _SHEET_ROWS_BUDGET:
                _con_nombre += 1                 # se sigue CONTANDO aunque ya no se liste
                continue
            # V2-455 — UN SOLO FORMATEADOR. Las tres reglas que aplica (la ausencia dicha, el teléfono como
            # dato accionable, la pista de búsqueda que no es candidato) costaron una ronda cada una y vivían
            # DUPLICADAS desde V2-451. Dos copias de una regla se separan sin avisar.
            _f = fila(i)
            out.append(_f)
            _chars += len(_f)
            _con_nombre += 1
        _tope = len(out)
        # V2-479 — CINCO FILAS ERAN POCAS, y está medido dos veces. `search-buy-camera__es` (V2-374) tenía
        # CATORCE candidatos y las cinco que llegaron eran cuatro accesorios; `find-best-hotel-city__us` ronda
        # 6 (2026-08-29) tenía DOCE hoteles con dos por debajo del tope del operador (€46 y €58) y las cinco
        # mostradas eran las caras — el turno concluyó «all well above your $150» sobre un conjunto que no
        # había visto entero. V2-374 ya añadía «y N más no listadas» y aun así concluyó: **decirle que hay
        # más no es enseñárselas**, y «di solo lo que RESPONDE a lo que pidió» sigue siendo imposible sobre lo
        # que no ve (V2-330). El coste es acotado y pequeño: ~100 caracteres por fila en el peor caso.
        # V2-374 — LO QUE QUEDA FUERA SE CUENTA. Es la segunda mitad de V2-234, que la nota del navegador ya
        # aplica desde entonces («y N filas más de la misma página») y esta cara nunca tuvo: cortaba en cinco y
        # se callaba, así que para el turno esas cinco ERAN la hoja entera.
        #
        # Medido en `search-buy-camera__es` (2026-08-27, 2/5). La hoja tenía CATORCE candidatos con nombre —
        # Canon EOS 4000D, Nikon D3500, D5300, Canon 7D, EOS 1200D, D50, D800— y las cinco que llegaron al
        # último turno fueron «Canon EOS 550D», «Funda Hama», «Mochila», «Arnés» y «Funda Kata». Cuatro de
        # cinco eran accesorios, y zaelar cerró la conversación ofreciendo la funda de 9 € y la mochila de 25 €
        # a quien pedía una réflex por menos de 400.
        #
        # No hay nada que reordenar y conviene decirlo: se comprobó contra el pipeline real y el orden que
        # llega es el del DOM, fielmente — fue Wallapop quien puso una funda la segunda. Con nueve filas
        # escondidas y sin saberlo, «di solo lo que RESPONDE a lo que pidió» es una instrucción que el prompt
        # hace difícil de cumplir: el modelo no puede elegir entre lo que no ve (V2-330).
        if _con_nombre > _tope:
            out.append(f"(y {_con_nombre - _tope} candidato(s) más con nombre en la hoja, no listados aquí)")
        return out

    except Exception:
        return []


def _site_of(url: str) -> str:
    """The site as a person would name it: `thefork.es`, not the whole URL.

    Measured on `restaurant-tonight-madrid` (2026-08-20 01:01): the task visited thefork.es, its Madrid list, a
    parked domain and finally casalucio.es, and every one of those reached the turn as a raw URL truncated to
    60 characters. The turn is read out loud, so a URL is not usable — and the block right next to it forbids
    describing what the task «would be doing». Between an unsayable fact and a ban, the model chose silence:
    «Sigo en ello» five times. The host is the part that is both TRUE and sayable.
    """
    from urllib.parse import urlparse
    try:
        host = (urlparse(str(url or "")).hostname or "").lower()
    except Exception:
        host = ""
    if not host:
        return str(url or "")[:60]
    return host[4:] if host.startswith("www.") else host


def navegador_lines() -> list[str]:
    """The STATE lines that talk about the browser — empty when there is nothing to report.

    Fail-open like the block it came from: a failure here must not leave the turn without state, so it returns
    whatever it has composed so far. That was the meaning of the `try/except: pass` around it in `live_state()`
    and is preserved — with one improvement: previously a mid-block failure took out the WHOLE block, whereas
    now already-composed lines survive.
    """
    lines: list[str] = []
    try:
        from widgets.navegador import tasks as _nt
        act = _nt.active_summaries()
        if act:
            # EXPLÍCITO (no solo "hay N"): el cerebro debe SITUARSE en lo que YA está haciendo para no relanzar
            # una búsqueda que ya corre (control de estado, 2026-07-12). Solo hay UN navegador para todo.
            #
            # V2-145 — y con lo que la tarea HA HECHO de verdad, no solo su objetivo. Antes esta línea decía que
            # existía y para qué, y nada más, así que «¿cómo va?» solo tenía los segundos para contestar: el
            # modelo los convirtió en detalle que no podía tener («lleva unos 2 minutos abierto en la página»,
            # «todavía interactuando») mientras el informe de esa misma tarea decía `url= events=[]` — no había
            # abierto NADA. La página y los pasos los escribe la propia tarea al conducir, así que vacíos no son
            # un hueco de nuestro conocimiento: son el hecho de que aún no ha pasado nada, y es lo que hay que
            # decir. Mismo remedio que `silent_s` en V2-131, una capa más abajo.
            try:
                _prog = {p["id"]: p for p in _nt.active_progress()}
            except Exception:
                _prog = {}
            _bits = []
            _blocked = _login = _has_results = ""       # el GOAL de la tarea que disparó cada cara, o ""
            _orphan = ""                                # …y la que se quedó SIN CONDUCTOR (V2-310)
            _rows: list[str] = []                       # …y las FILAS ya entregadas de esa misma tarea
            _asked: tuple | None = None                 # (goal, pregunta) de la tarea parada en el confirm-gate
            _hit_walls = ""                             # y la que YA se comió un bloqueo, aunque siga en otra página
            # V2-778 F1 — reading each live browser task lives in `live_blocks_nav.py`.
            _blk = _lbn.read_the_browser_tasks(
                _asked=_asked,
                _bits=_bits,
                _blocked=_blocked,
                _has_results=_has_results,
                _hit_walls=_hit_walls,
                _login=_login,
                _orphan=_orphan,
                _prog=_prog,
                act=act,
            )
            if '_asked' in _blk:
                _asked = _blk['_asked']
            if '_blocked' in _blk:
                _blocked = _blk['_blocked']
            if '_has_results' in _blk:
                _has_results = _blk['_has_results']
            if '_hit_walls' in _blk:
                _hit_walls = _blk['_hit_walls']
            if '_login' in _blk:
                _login = _blk['_login']
            if '_orphan' in _blk:
                _orphan = _blk['_orphan']
            if '_rows' in _blk:
                _rows = _blk['_rows']
            # V2-185: the reassuring half of this block used to be UNCONDITIONAL, and that is what kept the
            # operator waiting. Measured on `book-hotel-night-known__es` (2026-08-20 01:01): the wall DID reach
            # the turn — zaelar said «Booking me ha puesto una verificación anti-robot», which is the V2-167 fix
            # working — and then went back to «sigo con ello» for four more turns while the task sat on
            # `chrome-error://chromewebdata/`. It was not the model being lazy: this block was telling it, in
            # four sentences before the caveat, that «esa tarea sigue viva y te dará el resultado sola» and that
            # it must not push the operator to stop it. Both are FALSE in front of a wall, and the model
            # believed the longer, earlier half. So the promise is now conditional on the task being healthy.
            _head = f"NAVEGADOR — YA EN CURSO ({len(act)}): {'; '.join(_bits)}."
            # Se DICE, no se deja en el estado: el daño medido no fue que el sistema no lo supiera, fue que el
            # operador esperó diez turnos sin enterarse. Y se dice con el SITIO, que es la parte con la que él
            # puede hacer algo («pues mira en otra web», «lo compro yo»).
            _walls_note = ("" if not _hit_walls or _blocked else
                           f" A {_hit_walls} ya la han BLOQUEADO por el camino (ahí arriba, con qué y dónde): "
                           "aunque ahora siga en otra página, DÍSELO en cuanto pregunte cómo va, en vez de "
                           "«sigue sin dar señal» — que es cierto y no le sirve de nada. Un bloqueo es lo único "
                           "que explica la espera, y con el sitio delante él puede decidir (probar otra web, "
                           "mirarlo él, o dejarlo).")
            _shared = (" NO abras otra tarea ni reinicies la búsqueda para esto mismo — solo hay UN navegador. "
                       "Y NO describas lo que estaría haciendo («está en la página», «interactuando», "
                       "«rellenando el formulario»). Los segundos que lleva NO son una descripción de lo que hace.")
            # V2-778 F1 — saying what the brain may claim about the browser lives in `live_blocks_nav.py`.
            _blk = _lbn.say_the_browser_state(
                _asked=_asked,
                _blocked=_blocked,
                _has_results=_has_results,
                _head=_head,
                _login=_login,
                _orphan=_orphan,
                _rows=_rows,
                _shared=_shared,
                _walls_note=_walls_note,
                lines=lines,
            )
        # V2-150 — una tarea que TERMINA desaparecía del estado, así que no quedaba ningún hecho diciendo que
        # había acabado, y menos aún que había acabado vacía. El informe decía `status=done url=` mientras el
        # turno decía «los procesos siguen en marcha, llevan casi 5 minutos». No es el modelo inventando por
        # gusto: se le había quitado de delante lo único que podía contradecirle. Un FINAL es un hecho.
        try:
            _fin = _nt.recently_finished()
        except Exception:
            _fin = []
        if _fin:
            _fb = []
            for _f in _fin:
                _t = f"«{(_f.get('goal') or 'tarea')[:60]}»"
                # V2-196: pararse no es acabar. «Terminó sin traer nada» sobre algo que se CANCELÓ invita a
                # esperar un resultado que nadie va a producir; decir que se paró invita a preguntar si se
                # retoma, que es lo que el operador puede hacer con ese hecho.
                _st = str(_f.get("status") or "")
                if _st == "open":
                    # V2-197: no es un fracaso ni un resultado — es una pestaña que le abriste y ahí sigue.
                    # Decir «terminó sin traer nada» de algo que está delante suyo es negarle lo que tiene.
                    _t += " está ABIERTA en pantalla (se la abriste; ahí sigue)"
                elif _st == "cancelled":
                    _t += " se PARÓ (cancelada) sin llegar a terminar"
                else:
                    # V2-299 — «terminó SIN traer nada» se decidía por el registro de la TAREA (`has_results`,
                    # que solo existe si alguien llamó a `set_results`), y la hoja es de quien fía: measured
                    # 2026-08-24 with 21 named rows in the sheet, this line still read «SIN traer nada» — an
                    # active lie in the prompt, one step worse than the vanishing act V2-150 fixed. The SHEET
                    # rows win. And FINISHED may say «en la hoja»: the write already happened, which is exactly
                    # what V2-278 forbids claiming while the task is alive. Freshness is `recently_finished`'s
                    # own window — this branch only runs inside it.
                    _rows_f = _sheet_top_rows(_f.get("id") or "", 3)
                    if _rows_f:
                        _t += (" terminó CON resultado — en la hoja de resultados tiene: "
                               + "; ".join(_rows_f))
                    elif _f.get("has_results"):
                        _t += " terminó CON resultado"
                    else:
                        _t += " terminó SIN traer nada"
                if _f.get("last_event"):
                    _t += f" (lo último que vio: {_f['last_event'][:90]})"
                _fb.append(_t)
            lines.append(
                "NAVEGADOR — YA TERMINADO: " + "; ".join(_fb) + ". Eso YA NO está en marcha: si el operador "
                "pregunta, dilo —terminó, y con qué, NOMBRANDO lo de arriba con nombre y precio— y ofrece el "
                "siguiente paso; decir que «sigue procesando» o que «no hay nada» teniendo filas ahí arriba "
                "es contar algo que el sistema da por acabado. Y si lo último que vio responde a lo que te "
                "pidió (un teléfono, un horario, que solo se reserva llamando), DÁSELO: es el resultado, "
                "aunque no sea el que esperabas.")
        if _nt.login_waiting_id():
            lines.append("HAY UN INICIO DE SESIÓN PENDIENTE en el navegador (le abriste una ventana para entrar): "
                         "si el operador dice que ya inició sesión / 'ya estoy dentro', llama a login_done.")
    except Exception:
        pass
    return lines


def any_stalled_task() -> tuple[str, int, str]:
    """`(errand, minutes, reason)` for the first live STALLED task, or `("", 0, "")` when none is stalled.

    MISMA fuente y MISMOS umbrales que la cara de `pending_task_lines` — a propósito, y la razón está escrita
    en `dispatch_thresholds`: dos copias de estos números es cómo el operador acaba oyendo una cosa del aviso
    y otra del agente al que acaba de preguntar. Aquí se lee el mismo `pending_summaries()`.

    Existe para el backstop de V2-359: la cara ya ponía el hecho delante del modelo y el modelo lo contaba una
    vez de cada dos.
    """
    try:
        from nucleo import dispatch as _disp
        for t in _disp.pending_summaries():
            if str(t.get("waiting_on") or "") == "user":
                continue
            _silent = int(t.get("silent_s", 0) or 0)
            if _silent >= _disp.STUCK_SECS:
                return str(t.get("request") or ""), _silent // 60, "callada"
            if int(t.get("total", 0) or 0) and int(t.get("no_step_s", 0) or 0) >= _disp.NO_STEP_SECS:
                return str(t.get("request") or ""), int(t["no_step_s"]) // 60, "sin avanzar"
    except Exception:  # noqa: BLE001
        pass
    return "", 0, ""


def any_live_task_rows(n: int = 3) -> tuple[str, list[str]]:
    """`(goal, rows)` — the top NAMED rows of the FIRST live browser task whose sheet already has them, plus
    that task's goal. The reader the delivery backstop (V2-305, `delivery.sheet_delivery_backstop`)
    needs: same source as the face (`_sheet_top_rows`), so the backstop can never announce rows the prompt
    itself would not carry; the GOAL travels with them because the backstop's freshness test excludes the
    errand's own words (the category noun is in every turn by definition)."""
    try:
        from widgets.navegador import tasks as _nt
        for _tid, _g in _nt.active_summaries():
            rows = _sheet_top_rows(_tid, n)
            if rows:
                return str(_g or ""), [r.strip("«»") for r in rows]
    except Exception:  # noqa: BLE001
        pass
    return "", []




def harness_lines() -> list[str]:
    """V2-660 — open HARNESS goals travel as a fact WITH the rule (V2-453): a card the turn showed whose
    content is still missing must not be narrated as delivered by the next turn. Zero lines when none, and
    fail-open: a ledger that cannot be read costs the prompt nothing (extracted from `prompt.py`, V2-661)."""
    try:
        from nucleo import harness
        return list(harness.prompt_lines())
    except Exception:  # noqa: BLE001
        return []


def done_ops_lines() -> list[str]:
    """V2-707 F6 — WHAT THE ENGINE ALREADY DID TO HIS DATA, with its rule beside it (V2-453's lesson: the
    fact alone changes nothing).

    Measured 2026-09-16 (session 080b96a7, i=10817 and i=10853): two `clear_range` sweeps had run, nine rows
    were gone, and the turn said «In this conversation I never confirmed a deletion, so nothing has been
    removed from your calendar». That was a correct deduction from the only ledger it could see — the
    PENDING confirmations — because nothing carried the EXECUTED ones. The instruction matters as much as the
    fact: what he is disputing is not whether he said yes, it is whether it happened, and only one of those
    two is a thing we know.

    Zero lines when nothing ran, and fail-open: a ledger that cannot be read costs the prompt nothing.
    """
    try:
        from nucleo import done_ops as _done
        rows = _done.recent()
        if not rows:
            return []
        import time as _t
        # V2-778 F2-19 — an op the request record already shows (`recent_lines`) is not listed twice; what no row
        # shows (a CLICK on the card opens none) still is, and the two rules below stay whenever they apply.
        shown = _shown_by_requests()
        listed = [d for d in rows if not any(w == d["wid"] and a == d["action"]
                                             and abs(float(d.get("at") or 0) - at) <= 60 for w, a, at in shown)]
        away = sorted({d["wid"] for d in rows if not _is_open(d["wid"])})
        if not listed and not any(d.get("destructive") for d in rows) and not away:
            return []
        bits = []
        for d in listed or rows:
            ago = max(0, int(_t.time() - float(d.get("at") or _t.time())))
            n = d.get("n")
            bits.append(f"«{d['wid']}:{d['action']}»" + (f" ({n} fila/s)" if isinstance(n, int) else "")
                        + f" hace {ago}s")
        head = ("YA EJECUTADO SOBRE SUS DATOS en esta sesión (hechos del sistema, no de la conversación): "
                + "; ".join(bits) + ".")
        if any(d.get("destructive") for d in rows):
            return [head + " Eso YA PASÓ. Si el operador dice que has borrado o cambiado algo, TIENE RAZÓN: "
                    "no razones desde si hubo confirmación o no —eso es otra cosa— ni le digas que no se ha "
                    "tocado nada. Dile QUÉ se ejecutó y ofrécele deshacerlo o revisarlo."]
        # Demo pass 59 (S1): «results:present hace 140s» + «cuéntalo como hecho» over a sheet he had put away,
        # and «so how did the monitors go, show me» got «Done.» with the card still in the dock. Done to the
        # DATA is not on the SCREEN: a card that is not open now says so, with the one call that brings it.
        tail = (f" Ojo: {', '.join(away)} NO está en pantalla ahora — si pide verlo, `show_widget` lo trae; "
                "decir «hecho» sin traerlo es mentirle.") if away else ""
        return [head + " Si pregunta por ello, cuéntalo como hecho en vez de volver a hacerlo." + tail]
    except Exception:  # noqa: BLE001
        return []


def _shown_by_requests() -> list[tuple[str, str, float]]:
    """(widget, action, when) of the inline request rows the turn's record block already reports."""
    try:
        from nucleo import tasks as _tasks
        out = []
        for r in _tasks.store().tasks_where(states=("done", "failed", "running"), modes=("now",), visible_only=False,
                                            limit=24) or []:
            wa = str(r.get("outcome") or "")
            if r.get("kind") == "inline" and ":" in wa and " " not in wa:
                w, a = wa.split(":", 1)
                out.append((w.split("::", 1)[0], a, float(r.get("finished_at") or r.get("started_at") or 0)))
        return out
    except Exception:  # noqa: BLE001 — nothing readable: list everything, as before
        return []


def _is_open(wid: str) -> bool:
    """Whether a card of this widget (base id or any of its instances) is ON SCREEN now — open minus minimized
    (V2-776 L2, the one reader in `nucleo/truth.py`). Fail-open to True: a state that cannot be read must not
    add a warning that may be false."""
    try:
        from nucleo import truth as _truth
        state = _truth.canvas_state(wid)
    except Exception:  # noqa: BLE001
        return True
    return True if state is None else state in ("visible", "maximized")


from nucleo.flash.task_block import _short_note, pending_task_lines, recent_lines  # noqa: E402,F401 — re-export


def _job_line(j: dict) -> str:
    """One scheduled job for the prompt: its bell, and — when it is an appointment's notice — the appointment."""
    import re as _re
    # A date followed by a time, whatever words sit between them — the notice's text is in HIS language.
    m = _re.search(r"(\d{4}-\d{2}-\d{2})\D{1,16}?(\d{1,2}:\d{2})", str(j.get("prompt") or ""))
    when = f"la cita es el {m.group(1)} a las {m.group(2)}; " if m else ""
    return f"{j.get('name')} ({when}el aviso suena {j.get('schedule')})"


def _cron_line() -> str:
    """One line of proactivity (cron tags) plus anything already scheduled, if present. Concise (V2-027).

    The RULE that "a spoken reminder is not a reminder" comes from the `remember-and-remind-deadline` use case
    (V2-121, run 2026-08-18): when told "write it down for Thursday… and remind me on Wednesday," the brain
    answered "Done" and kept claiming in later turns that it was scheduled, with ZERO mechanism behind it. This
    was not model oversight: the catalog literally said a reminder was "acknowledged without a tool," so the
    measured behavior was what the prompt requested. This says the opposite, using the absolute-date format
    `scheduler.parse_schedule` already understands so a specific day can be EXPRESSED in one pass."""
    line = ('Proactividad (recordatorios/tareas programadas): [[cron.create]]'
            '{"schedule":"30m|every 2h|2026-08-19 09:00|0 9 * * *","prompt":"qué avisar","name":"…"}'
            '[[/cron.create]] · [[cron.cancel:name]]. `schedule` admite un plazo relativo, una FECHA ABSOLUTA '
            '(YYYY-MM-DD HH:MM, para un aviso de una sola vez en un día concreto — la fecha la sacas de la lista '
            'de días de tu ESTADO, no la calcules a ojo) o un cron de 5 campos si es RECURRENTE. '
            'Una ORDEN con plazo NO es pedir un recordatorio: «paga la factura antes del día 5» es HACERLO (y si es irreversible, preguntar antes) — apuntarlo en su lugar es no atenderle. REGLA DURA: si el operador pide que le AVISES/RECUERDES algo en un momento dado, emite la tag EN '
            'ESE TURNO — decir «te lo recuerdo» sin ella no programa nada y es mentirle. Y si el compromiso '
            'tiene fecha, apúntalo en su agenda (widget_data add_meeting) — la cita CREA SOLA su aviso por '
            'defecto, así que NO emitas además un cron para la misma cita; para cambiarle la hora al aviso es '
            'widget_data set_reminder. La tag es para avisos SUELTOS sin cita detrás. Si te falta la hora o el '
            'día exacto, PREGUNTA antes de programar.')
    try:
        from nucleo import scheduler
        jobs = scheduler.list_jobs(active_only=True)
        if jobs:
            # The time is when the ALERT rings, not when the thing happens (demo pass 2026-09-28, Z1: «ZAELAR
            # weekly review (2026-09-29 07:00)» — the meeting's own 2-hours-early alert — was read back to him as
            # the meeting at 7). The datum says what it is; the meeting's time lives on the agenda.
            # Saying so was not enough (full16 C1: «review at 7, product at 9, meshcore at 1» — every alert
            # time read as its meeting, and C2 then booked Rowan on top of the 3 pm meeting it «ended at 2»).
            # A notice that belongs to an appointment names the appointment's own time next to its bell.
            # …and it is NOT the day's agenda (full25 Z1: «what's on my plate tomorrow» was answered from this line —
            # two of the four meetings, because six notices is not a calendar). Soonest first, and it says so.
            jobs = sorted(jobs, key=lambda j: str(j.get("next_run") or j.get("schedule") or ""))
            line += (" Ya programado (hora a la que SUENA el aviso, no la de la cita — una lista PARCIAL de avisos, "
                     "NO la agenda: lo que hay un día se lee en la agenda con read_widget, nunca de aquí): "
                     + "; ".join(_job_line(j) for j in jobs[:6]) + ".")
    except Exception:
        pass
    return line


def shelf_lines() -> list[str]:
    """The finished errands' sheets he can ask for by what they show — closed, and one `show_widget` away.

    V2-773 (demo S1, 2026-09-27): the monitor errand had finished, its sheet was closed, and «Show me the
    monitors» read «no monitor widget in your setup» — a second worker went to search the same monitors again.
    The sheet was on disk the whole time; the model had no name for it. Three at most, most recent first,
    open ones left out (they are already on screen)."""
    try:
        from memory import api as _memapi
        from widgets import instances as _inst
        open_now = {str(w).strip() for w in ((_memapi.state() or {}).get("open_widgets") or [])}
        rows = [r for r in _inst.recent_faces(5) if str(r.get("id")) not in open_now][:3]
    except Exception:  # noqa: BLE001
        return []
    if not rows:
        return []
    names = " · ".join(f"«{str(r['label'])[:60]}» ({r['id']})" for r in rows)
    return [f"HOJAS CERRADAS de encargos ya hechos, que puede pedir por lo que muestran — `show_widget` con ese id "
            f"la trae de vuelta, sin buscar nada de nuevo: {names}."]


from nucleo.flash import live_blocks_nav as _lbn  # noqa: E402 — V2-778 F1, reads this module back
