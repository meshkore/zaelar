"""nucleo/flash/live_blocks.py — el ESTADO VIVO del NAVEGADOR, renderizado (V2-276).

Extraído de `prompt.live_state()` el 2026-08-24 para pagar el trinquete de arquitectura
(`test_architecture_ratchet`), que llevaba rojo desde los commits de la noche anterior: `prompt.py` estaba 56
líneas por encima de su techo y la regla de esa tabla es explícita — un fichero que crece pide EXTRAER un
módulo, nunca subir el número.

Se eligió este trozo y no otro porque la frontera ya existía: es el único de los tres bloques de `live_state()`
que se compone ENTERO a partir del registro del navegador (`widgets.navegador.tasks`) y no comparte un solo
dato con los otros dos. Sus tres ayudantes —el umbral de atasco, el nombre legible del sitio y la señal de
«ya encontró algo»— no tienen ningún otro llamante en el motor, así que viajan con él.

Se re-exportan desde `prompt` porque hay tests que los importan por nombre desde allí, y porque el
contrato público sigue siendo `live_state()`: esto es una mudanza, no un cambio de interfaz.

Las CARAS del bloque (pregunta pendiente · ya tiene resultados · parada esperando login · bloqueada · sana) y
el porqué de cada una siguen documentados donde se aplican, abajo. El nodo 4.21
(`test_every_face_is_reachable`) recorre este fichero exigiendo que cada una pueda dispararse de verdad.
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
    """¿Este paso del worker afirma algo sobre la hoja del operador que la hoja no respalda?

    `sheet` es la hoja del ENCARGO (`sheets.sheet_of(rec)`), no la de una pestaña: el paso lo escribe el
    worker sobre lo SUYO. Sin hoja resuelta se responde que NO — marcar por no saber leer sería acusar a
    ciegas, y el silencio de este detector deja el anillo exactamente como estaba.
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


from nucleo.flash.errand_sheet import _sheet_of_tab, aviso_sin_filas, boxes_of_tab   # V2-432


def _sheet_has_rows(nav_task_id: str) -> bool:
    """¿Hay ya filas CON NOMBRE en la hoja de este encargo?

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
    """¿Esta pestaña se quedó SIN CONDUCTOR? (V2-310)

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


def _sheet_top_rows(nav_task_id: str, n: int = 5) -> list[str]:
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
        for i in (_sheet.view_data(sheet) or {}).get("items") or []:
            title = str((i or {}).get("title") or "").strip()
            if not title:
                continue
            if len(out) >= max(1, int(n)):      # se sigue CONTANDO aunque ya no se liste
                _con_nombre += 1
                continue
            price = str((i or {}).get("price") or "").strip()
            # V2-360 — LA AUSENCIA, DICHA. Sin esto una fila sin importe se renderiza como un título a secas y
            # el modelo tiene que deducir del SILENCIO que no hay precio; medido en `compare-insurance-quotes__es`
            # (2026-08-27): de cuatro filas solo una traía importe, y el turno anunció «Direct, Allianz Direct,
            # Génesis, MAPFRE y Pelayo… estas tres primeras ya te sirven» — nombres sin dato presentados como
            # presupuestos comparables. Es el mismo remedio que V2-127 («AUSENCIA de ubicación, dicha con todas
            # las letras») y V2-133 («SIN paso reportado aún»): nombrar el hueco cuesta una palabra y cierra la
            # sustitución. Un teléfono cuenta como importe a estos efectos — misma regla que `by_amount`: un
            # resultado es un nombre y una forma de actuar sobre él, nunca un precio (V2-240).
            _tel = str((i or {}).get("tel") or "").strip()
            _facts = [f for f in ((i or {}).get("facts") or []) if isinstance(f, dict)]
            if not _tel:
                _tel = next((str(f.get("value") or "").strip() for f in _facts
                             if str(f.get("label") or "").strip().lower().startswith("tel")), "")
            # V2-376 — una PISTA de búsqueda web no es un candidato sin precio: es una página que quizá lleve
            # al candidato. Llamarla «SIN PRECIO» la presenta como una ficha a la que le falta un dato, y así
            # es como acaban ofreciéndose «9 precios y ofertas 2026» y «Top actividad en Bilbao» como planes.
            _pista = any(str(f.get("value") or "").strip().lower() == "búsqueda web"
                         and str(f.get("label") or "").strip().lower() == "origen" for f in _facts)
            if price:
                _dato = price[:20]
            elif _tel:
                _dato = _tel[:20]
            elif _pista:
                _dato = "PÁGINA WEB por mirar, aún no es un candidato"
            else:
                _dato = "SIN PRECIO"
            out.append("«" + title[:70] + " — " + _dato + "»")
            _con_nombre += 1
        _tope = max(1, int(n))
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
    """Las líneas del ESTADO que hablan del navegador — vacío si no hay nada que contar.

    Fail-open como el bloque del que sale: un fallo aquí no puede dejar al turno sin estado, así que devuelve
    lo que llevara compuesto. Esa era la semántica del `try/except: pass` que lo envolvía en `live_state()` y
    se conserva tal cual — con una diferencia a favor: antes un fallo a mitad se llevaba por delante TODO el
    bloque, y ahora las líneas ya compuestas sobreviven.
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
            for _tid, _g in act:
                _b = f"«{(_g or 'tarea')[:70]}»"
                _p = _prog.get(_tid) or {}
                # V2-302 — la EDAD como hecho, siempre que se sepa. A los 21 s de vida el turno dijo «lleva un
                # rato sin reportar nada… ¿prefieres que la pare?» (ronda 29): sin la edad delante, el modelo
                # rellenó el hueco con «un rato» y le ofreció al operador matar una tarea recién nacida.
                _age = int(_p.get("age_s") or 0) if _p else 0
                if _age > 0:
                    _b += (f" (arrancó hace {_age} s)" if _age < 90 else
                           f" (arrancó hace {_age // 60} min)")
                if _p:
                    if _p.get("url"):
                        # V2-187: the SITE, not the raw URL. What the state handed the turn was
                        # «en https://www.thefork.es/restaurantes/madrid» — a string nobody says out loud, so
                        # the turn said nothing instead: five consecutive «sigo en ello» while the task was
                        # measurably on El Tenedor and then on Casa Lucio's own site. A host is sayable.
                        _b += f" — en {_site_of(_p['url'])}"
                        if _p.get("steps"):
                            _b += f", {_p['steps']} pasos dados"
                    else:
                        # V2-152: this used to read «TODAVÍA NO HA ABIERTO NINGUNA PÁGINA», stated as a fact
                        # about the world. Measured on the run: the worker was on Booking.com with the hotel name
                        # already typed while the brain reported to the operator that nothing had been opened —
                        # and the operator, reasonably, killed a task that was progressing. An empty record is
                        # the absence of a REPORT, not the absence of work: the record is only written when the
                        # browser is driven through certain actions, and a worker that is planning, reading a
                        # capture or thinking writes nothing at all. So say what is true — no news — and keep
                        # V2-145's real guarantee, which was never the wording but the ban on inventing detail.
                        _b += " — AÚN NO HA REPORTADO NINGÚN PASO (no sabes si está pensando o atascada)"
                    # V2-150: el ÚLTIMO HITO, no solo cuántos lleva. La corrida descubrió «Casa Lucio solo
                    # acepta reservas por teléfono» y el operador se enteró al final, cuando pidió pararlo:
                    # el hito estaba en la tarea desde el principio y al cerebro le llegaba un CONTADOR de
                    # pasos. Un número no se puede decir en voz alta.
                    # V2-187: a milestone that only says «opened <url>» on the site ALREADY named two words
                    # earlier adds nothing and puts a second unsayable URL in front of the turn. Everything
                    # else stays — V2-150 exists precisely because a real milestone («Casa Lucio solo acepta
                    # reservas por teléfono») was the thing the operator needed and never got.
                    _le = str(_p.get("last_event") or "")
                    if _le and not (_le.startswith("🌐") and _site_of(_le.split()[-1]) == _site_of(_p.get("url") or "")):
                        _b += f" · último: {_le[:90]}"
                    # V2-167 — the two facts that turn «no tengo novedades» into something the operator can act
                    # on. Three measured runs ended `status=working results=null` with the operator giving up:
                    # the restaurant sat 11 minutes on the right page, the hotel 3 minutes on Booking's anti-bot
                    # challenge, the theatre passed through a CAPTCHA. In all three the brain told the truth and
                    # the truth was useless, because the only truth it had was that the task was alive.
                    # V2-176 frente 3: esperar a que el operador ENTRE es lo más parecido a un muro que hay,
                    # y el único que se quita solo… si alguien se lo dice. `active_progress()` lo expone desde
                    # V2-167 y este bloque no lo leía nunca, así que una tarea parada en el login convivía con
                    # «te dará el resultado sola»: el operador esperaba a la tarea y la tarea al operador.
                    # V2-192 — REGRESIÓN PROPIA, medida el 2026-08-20 02:22 en `find-theatre-tickets__es`:
                    # «ocultó al usuario que había encontrado datos reales y afirmó falsamente que la tarea
                    # estaba paralizada». Un worker que encuentra los datos y hace una pausa —extrayendo,
                    # componiendo, esperando— cruza los 120 s sin cambiar de URL, y V2-185 lo declaraba
                    # BLOQUEADO. Antes de V2-185 el estado era demasiado OPTIMISTA («te dará el resultado
                    # sola») y con V2-185 pasó a ser demasiado PESIMISTA; las dos son falsas cuando lo cierto
                    # es que ya hay algo que entregar. Tener resultados gana a cualquier medida de atasco.
                    # V2-193: con VARIAS tareas vivas hay que saber CUÁL disparó la cara. El imperativo decía
                    # «ESA TAREA» a secas, y con tres en marcha eso apunta a cualquiera — medido en
                    # `renew-gym-membership__es` (2026-08-20 02:28): «desviaciones de atención severas
                    # (distracción con tareas de navegador no solicitadas), mezclando dominios (Netflix/Teatro)
                    # al preguntar por el gimnasio». El estado le MANDABA entregar el teatro mientras el
                    # operador preguntaba por su gimnasio.
                    _who = f"«{(_g or 'la tarea')[:50]}»"
                    # V2-200 — `has_results` en la tarea NUNCA es cierto mientras está viva: los TRES sitios
                    # que llaman a `set_results()` llaman a `finish()` acto seguido (`owner.py`,
                    # `dispatch._finalize_web`, `web_cc`). O sea que la cara «YA TIENE RESULTADOS» de V2-192 era
                    # código muerto, y sus tests pasaban porque creaban un estado que producción no produce —
                    # exactamente el fallo de V2-199, encontrado con el mismo método.
                    #
                    # La señal VIVA de que el worker ya encontró algo sí existe, en el otro registro: la
                    # amplitud que él mismo reporta (`hbnote considered --kept N`). Se lee por el seam que ya
                    # había (`dispatch.record_by_nav_task`), no por uno nuevo.
                    # V2-202 — una PREGUNTA sin contestar gana a cualquier otra cara: la tarea no está lenta ni
                    # bloqueada por fuera, está esperando una palabra del operador que nadie le ha pedido.
                    if _p.get("question"):
                        _b += f" · TE ESTÁ PREGUNTANDO: {_p['question'][:120]}"
                        _blocked = True
                        _asked = _asked or (_who, _p["question"])
                    elif _p.get("has_results") or _found_candidates(_tid):
                        _b += " · YA HA ENCONTRADO ALGO"
                        if not _has_results:
                            _has_results = _who
                            _rows = _sheet_top_rows(_tid)
                    # V2-310 — SIN CONDUCTOR gana a login/muro/atasco: si el worker murió, que el operador
                    # entre en la web o que la página desbloquee no sirve de nada; nadie va a seguir. Pierde
                    # contra `question` y `has_results`, que siguen siendo lo más útil que decir (y el hecho
                    # se anota igual abajo, fuera del elif, para que la frase no mienta).
                    elif _driver_is_gone(_tid, _p):
                        _b += " · SU WORKER MURIÓ: la pestaña sigue abierta pero NO la conduce nadie"
                        _orphan = _orphan or _who
                    elif _p.get("awaiting_login"):
                        _b += " · PARADA ESPERANDO A QUE ENTRES TÚ (hay una ventana abierta para iniciar sesión)"
                        _blocked = True
                        _login = _login or _who
                    elif _p.get("wall"):
                        _b += f" · MURO: {_p['wall']}"
                        _blocked = _blocked or _who
                    # V2-308 — «SIN MOVERSE de esa página» exige que HAYA una página. `stalled_s` se mide
                    # desde `last_progress or created`, así que una tarea que aún no ha dado su PRIMER paso
                    # acumula atasco desde que nació y a los dos minutos se declaraba BLOQUEADA. Medido en la
                    # ronda de las 04:35 (2026-08-25), y el bloque se contradecía a sí mismo en la MISMA
                    # línea: «AÚN NO HA REPORTADO NINGÚN PASO (no sabes si está pensando o atascada)» seguido
                    # de «ESTÁ BLOQUEADA … es un HECHO medido». El modelo creyó a la mitad fuerte, dijo que la
                    # búsqueda estaba muerta y ofreció relanzarla CUATRO veces con el operador prohibiéndoselo
                    # — es V2-152 por el otro lado (allí se afirmaba que no había abierto nada; aquí que se
                    # había quedado parada en una página que no existe). Sin url y sin pasos no hay atasco que
                    # medir: hay una tarea sin señal, que ya tiene su redacción propia en la rama sana.
                    elif int(_p.get("stalled_s") or 0) >= _STALLED_S and (_p.get("url") or _p.get("steps")):
                        _b += f" · lleva {int(_p['stalled_s']) // 60} min SIN MOVERSE de esa página"
                        _blocked = _blocked or _who
                    # LOS MUROS QUE YA SE COMIÓ, aunque ahora esté en otra página. Va FUERA del elif: no es
                    # una cara alternativa de la tarea, es historia suya, y compone con cualquiera de las de
                    # arriba. Medido en `find-theatre-tickets__es` (12:39): el detector de muro disparó de
                    # verdad, el worker se re-enrutó —correcto— y el hecho se borró con el siguiente `update_view`,
                    # así que zaelar pasó diez turnos diciendo «sigue sin dar señal de dónde está».
                    if not _orphan and _driver_is_gone(_tid, _p):
                        # El hecho compone con CUALQUIER cara (V2-176 con los muros): con resultados delante
                        # la cara correcta sigue siendo entregarlos, pero decir «no está bloqueada ni
                        # esperando» sobre una pestaña sin conductor sería la contradicción de nuevo.
                        _b += " (su worker murió: nadie la conduce)"
                        _orphan = _who
                    if int(_p.get("walls_hit") or 0) and not _p.get("wall"):
                        _lw = _p.get("last_wall") or {}
                        _n = int(_p["walls_hit"])
                        _site_lw = str(_lw.get("site") or "")
                        _b += (f" · ya se topó con {_n} bloqueo{'s' if _n > 1 else ''}"
                               + (f" (el último: {_lw.get('reason')}" + (f" en {_site_lw}" if _site_lw else "")
                                  + ")" if _lw.get("reason") else ""))
                        _hit_walls = _hit_walls or _who
                _bits.append(_b)
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
            if _asked:
                # V2-202 — la cara MÁS urgente y la única que el operador puede resolver en una palabra. Va
                # primero a propósito: una tarea parada en el confirm-gate no está lenta, está esperándole a
                # él, y él no lo sabe porque nadie se lo ha preguntado.
                lines.append(
                    _head + f" {_asked[0]} ESTÁ PARADA ESPERANDO TU OK y el operador NO LO SABE: nadie le ha "
                    f"preguntado todavía. PREGÚNTASELO EN ESTE TURNO, literalmente: «{_asked[1][:140]}». No es "
                    "charla ni un trámite que puedas dar por hecho — sin su sí no se pulsa nada, y sin su "
                    "respuesta la tarea se cae sola dentro de unos minutos. Cuando conteste, su sí o su no ES "
                    "la respuesta a esto: no lo trates como una petición nueva." + _shared)
            elif _has_results:
                # V2-278 — «tiene resultados EN LA HOJA» es una afirmación sobre la PANTALLA, y esta cara
                # dispara con dos señales que no dicen lo mismo: `has_results` (la tarea acabó y se escribió) y
                # la amplitud viva del worker (`kept`, V2-200), que solo dice que ha ENCONTRADO. Medido en
                # `search-secondhand-monitor__es` (2026-08-24 01:47): el turno dijo «Ya tengo resultados EN
                # PANTALLA» a los 130 s y la primera fila se escribió a los 142 — doce segundos de una
                # afirmación falsa sobre lo que el operador tiene delante, que es justo la familia que V2-209
                # cerró para el ack de «Aquí lo tienes».
                # Lo que el cerebro SÍ sabe es qué encontró. Dónde está eso es otro hecho, y no lo tiene.
                # Y las FILAS van AQUÍ MISMO, porque sin ellas el imperativo de abajo es incumplible: la nota
                # que las llevó al cerebro fue de UN turno, y en el siguiente ya no está. Medido en
                # `search-buy-guitar__es` (ronda 21): 27 candidatas en la hoja 250 s antes del último turno y
                # el modelo contestando «déjame ver» porque no tenía delante ni una.
                _rows_bit = ""
                if _rows:
                    # Round 22 (2026-08-24) taught the second half: «dilo tal cual» made the turn recite a
                    # 2.490 € Gibson and a case+humidifier against a «menos de 150 €» errand — the sheet holds
                    # everything the page gave, and the JUDGING of what answers the errand belongs to the
                    # turn, not to the recital. Same rule as the V2-223 note: hand over the facts AND name
                    # the test.
                    _rows_bit = (" LO QUE YA HA ENTREGADO (nombre y precio, de la hoja): " + "; ".join(_rows) +
                                 ". OJO: la hoja guarda TODO lo que dio la página — di solo lo que RESPONDE "
                                 "a lo que pidió (precio dentro del tope, la cosa pedida y no un accesorio); "
                                 "lo que no encaje no lo ofrezcas como resultado. Si pregunta por un dato que "
                                 "estas líneas no traen (zona, estado, año), di honestamente que ese dato aún "
                                 "no ha llegado y ofrece el que sí tienes — nunca contestes «déjame mirar» "
                                 "teniendo esto delante. Y una línea marcada SIN PRECIO no es una opción "
                                 "comparable: puedes nombrarla como pista de por dónde va la cosa, pero NO la "
                                 "ofrezcas como candidata al lado de las que sí traen importe, ni digas que "
                                 "«ya te sirve» para elegir.")
                # V2-330 — SI NO HAY FILAS, NO SE PUEDE PEDIR QUE LAS CUENTE. La orden de abajo dice
                # «CUÉNTALE lo que encaje, con nombre y precio», y `_rows_bit` solo existe cuando la hoja ya
                # tiene filas con nombre. Sin ellas el turno recibe un imperativo IMPOSIBLE, y el modelo
                # contesta lo único honesto que puede: «te aviso en cuanto tenga algo».
                #
                # Medido sobre los turnos del plató (2026-08-25, 21:00 en adelante), contando solo los turnos
                # en los que esta cara dispara:
                #     SIN filas en el prompt : 14 turnos · 79 % responden con espera
                #     CON filas en el prompt : 45 turnos · 42 % responden con espera
                # El 79 % no es desobediencia — es la única salida que le dejamos. Y así se leía desde fuera:
                # cinco de los diez casos con mecanismo ≥4 y resultado ≤3 traen este veredicto, y el de
                # `search-buy-camera__es` cita la instrucción por su nombre: «el modelo ignora que la tarea ya
                # tiene resultados (instrucción 'CUÉNTALE') y miente diciendo que sigue buscando».
                #
                # Es la trampa que el propio docstring de `_sheet_top_rows` nombra desde V2-298: «una
                # instrucción que el prompt hace imposible de cumplir no es una instrucción — es una trampa
                # para el modelo Y para quien lea el transcript». La escribimos nosotros.
                #
                # La rama va DENTRO del imperativo (norma del operador), y lo que pide es lo que SÍ se puede
                # hacer con lo que hay: el HECHO de que está produciendo, sin prometer detalles que no tiene.
                if not _rows_bit:
                    lines.append(
                        _head + f" {_has_results} YA HA ENCONTRADO algo: no está bloqueada ni esperando, pero "
                        "sus nombres AÚN NO están escritos, así que no los tienes. Dile eso tal cual —que ya "
                        "está sacando cosas y que en cuanto tenga los nombres se los pasas—, sin inventarte "
                        "ninguno y sin prometer un detalle concreto. NO digas que sigue «sin resultados» ni "
                        "que «no ha encontrado nada»: eso es falso y es lo contrario de lo que pasa." +
                        _shared + _walls_note)
                elif True:
                    lines.append(
                            _head + f" {_has_results} YA HA ENCONTRADO algo: no está bloqueada ni esperando. CUÉNTALE "
                        "en este turno LO QUE ENCAJE con lo que pidió —con nombre y precio, no que «ya casi "
                        # V2-318 — LA BIFURCACIÓN VA DENTRO DEL IMPERATIVO. La cabeza decía «CUÉNTASELO: QUÉ ha
                        # encontrado» y el bloque de filas decía «di solo lo que RESPONDE a lo que pidió»: dos
                        # órdenes en tensión, y gana la primera por ser imperativa y venir antes. Medido en la
                        # ronda 37 de la guitarra (2026-08-25 15:51), turno 10: con TRES filas en la hoja y
                        # ninguna válida, recitó las tres en orden crudo contra un encargo de «acústica por
                        # debajo de 150» — una clásica de 200 €, un COLGADOR de guitarra de 5 € y una Taylor de
                        # 700 €. Seis turnos después, ya con muchas filas, filtró perfectamente («las que no son
                        # guitarras —estuche, CD, luthier— y la de 350 € las descarto»). O sea que sabe filtrar:
                        # lo que no sabía es qué decir cuando el filtro se lo lleva TODO, y ahí el reflejo es
                        # entregar lo que hay. La rama que faltaba es esa, y es la única forma de que el
                        # imperativo no se contradiga a sí mismo (norma del operador: una instrucción por bloque).
                        "está»— y pregunta si le vale o quiere que sigas afinando; y si de estas líneas NINGUNA "
                        "encaja, dile eso mismo —que van saliendo cosas y de momento ninguna cumple lo que pidió, "
                        "y que sigues— en vez de ofrecerle la que menos desencaja." + _rows_bit +
                        " NO digas que «lo tiene en pantalla» ni «en la "
                        "hoja»: eso es otra cosa y puede tardar unos segundos más en escribirse; di lo que hay, "
                        "que es lo que sabes. Decirle que está parada teniendo datos delante es la "
                        "misma mentira que decirle que sigue buscando cuando ya no busca." + _shared + _walls_note)
            elif _orphan:
                # V2-310 — y aquí SÍ se ofrece relanzar, justo al revés que en V2-308: allí la tarea estaba
                # ARRANCANDO y ofrecer abandonarla la mataba; aquí no queda nadie conduciendo, así que
                # relanzar es lo ÚNICO que puede traer el resultado. La frase nombra el hecho y no lo
                # disfraza: el operador estaba esperando a un encargo sin dueño.
                lines.append(
                    _head + f" {_orphan} SE QUEDÓ SIN CONDUCTOR: el proceso que la llevaba ha muerto (se le "
                    "acabó el plan del proveedor, o falló) y la pestaña sigue abierta sin que nadie avance. "
                    "NO va a terminar sola y esperar no sirve de nada. DILO en este turno —aunque el operador "
                    "acabe de decir que espera tranquilo— y ofrécele RELANZARLA; si él dice que no la "
                    "relances, respétalo y no vuelvas a proponerlo, pero tampoco digas que sigue en marcha."
                    + _shared + _walls_note)
            elif _login:
                lines.append(
                    _head + f" {_login} ESTÁ PARADA Y SOLO LA DESBLOQUEA ÉL: no va a avanzar ni un paso "
                    "hasta que el operador inicie sesión en la ventana que tiene abierta. DÍSELO en este turno, "
                    "aunque acabe de decir que espera tranquilo, y con las palabras exactas de lo que tiene que "
                    "hacer («tienes una ventana abierta en X, entra con tu cuenta y me lo dices»). NO es un "
                    "fracaso: pararse en su login es lo correcto, y ahora mismo es lo ÚNICO que falta. Callarlo "
                    "es dejarle esperando a una tarea que está esperándole a él." + _shared + _walls_note)
            elif _blocked:
                lines.append(
                    _head + f" {_blocked} ESTÁ BLOQUEADA: lo que pone arriba de ella (MURO / «sin moverse») es un "
                    "HECHO medido, no "
                    "falta de novedades, y esa tarea NO va a terminar sola. DILO en este turno, aunque el "
                    "operador acabe de decir que espera tranquilo —esperar es justo lo que hará si te callas— y "
                    "con una salida concreta: probar en otro sitio, que entre él, o dejarlo. Repetir «sigo con "
                    "ello» encima de un muro es dejarle esperando algo que ya no va a llegar. "
                    "Nunca esperes callado sobre un muro." + _shared)
            else:
                lines.append(
                    _head + " Esa tarea sigue viva y te dará el resultado sola. "
                    # V2-302: la edad va arriba entre paréntesis y se usa TAL CUAL — el daño medido fue el
                    # relleno («lleva un rato») y la oferta de matar una tarea de 21 segundos.
                    "La EDAD de la tarea está arriba («arrancó hace…»): úsala tal cual si hablas de tiempo. "
                    "Una tarea de menos de un minuto está ARRANCANDO: no digas que «lleva un rato», no "
                    "sugieras que «puede que esté costando» y NO ofrezcas pararla o relanzarla — una búsqueda "
                    "normal tarda 2-3 minutos en traer sus primeros candidatos. Si el operador "
                    "añade un matiz (precio, zona, «analízalas una por una»), reconócelo («sigo con ello, lo "
                    "tengo en cuenta») — NO escalas de nuevo. "
                    "Lo que ves AQUÍ es TODO lo que sabes de ella, y no saber NO es saber que no hace nada: si "
                    "no ha reportado ningún paso, di que aún no tienes novedades suyas —nunca que no ha hecho "
                    "nada ni que está atascada—. "
                    # V2-187: sin esta frase el bloque solo PROHÍBE, y el modelo se refugia en «sigo en ello».
                    # El sitio y el último paso están AHÍ arriba: son hechos, no descripciones inventadas.
                    "Pero si arriba SÍ pone dónde está o cuál fue su último paso, eso es un HECHO y se DICE en "
                    "vez de «sigo en ello» («está en El Tenedor», «ha llegado al formulario de reserva»): repetir "
                    "un relleno teniendo un dato concreto delante es lo que hace que el operador deje de creerte. "
                    # V2-152: no news is NOT a stall. Intact, and now it only applies where it is TRUE.
                    "Y si el operador se plantea pararla, no le empujes a hacerlo por falta de novedades: dile "
                    "que sigue viva y que la falta de parte no significa que esté parada." + _shared + _walls_note)
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
    """`(encargo, minutos, motivo)` de la primera tarea viva ATASCADA, o `("", 0, "")` si ninguna lo está.

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
                if _silent >= _disp.STUCK_SECS:
                    bit += f" — ENCALLADA: {_silent // 60} min SIN DAR NINGUNA SEÑAL"
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
                    bit += f" — YA HA ENCONTRADO {_kept} candidato(s)"   # V2-278: cuántos, nunca DÓNDE
                bits.append(bit + f' (llevas {t.get("secs", 0)}s)')
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
                         "esas letras la primera vez que salga a colación y ofrece pararla — NO respondas "
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
                         "EN PANTALLA, o que YA HA ENCONTRADO candidatos, entonces la tarea SÍ ha traído "
                         "eso — cuéntalo en este turno, di qué "
                         "hay y qué falta todavía, y NO contestes «sigo con ello». Lo que sigue EN CURSO es "
                         "la tarea, no lo que ya está entregado; negar una entrega que el operador tiene "
                         "delante en la pantalla es peor que no haberla hecho. "
                         # V2-348, cuarta cara — y la SIMÉTRICA, medida en `search-buy-used-car` ronda 8
                         # (2026-08-26). El paso decía «coches.net caído tras portada (página de error)» y el
                         # turno contestó «está entrando en el marketplace y ya va dando pasos. No ha sacado
                         # coches aún, pero no está atascada». Ni una palabra del sitio que se había caído. No
                         # es desobediencia otra vez: el bloque tenía rama para ENCALLADA, para SIN paso y para
                         # ENTREGADO — solo las buenas noticias llevaban un «cuéntalo». La asimetría estaba
                         # AQUÍ, así que el modelo relató la mitad que el bloque nombraba.
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
