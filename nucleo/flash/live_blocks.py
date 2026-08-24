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
        return bool(rec) and int(getattr(rec, "kept", 0) or 0) > 0
    except Exception:
        return False


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
            _asked: tuple | None = None                 # (goal, pregunta) de la tarea parada en el confirm-gate
            _hit_walls = ""                             # y la que YA se comió un bloqueo, aunque siga en otra página
            for _tid, _g in act:
                _b = f"«{(_g or 'tarea')[:70]}»"
                _p = _prog.get(_tid) or {}
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
                        _has_results = _has_results or _who
                    elif _p.get("awaiting_login"):
                        _b += " · PARADA ESPERANDO A QUE ENTRES TÚ (hay una ventana abierta para iniciar sesión)"
                        _blocked = True
                        _login = _login or _who
                    elif _p.get("wall"):
                        _b += f" · MURO: {_p['wall']}"
                        _blocked = _blocked or _who
                    elif int(_p.get("stalled_s") or 0) >= _STALLED_S:
                        _b += f" · lleva {int(_p['stalled_s']) // 60} min SIN MOVERSE de esa página"
                        _blocked = _blocked or _who
                    # LOS MUROS QUE YA SE COMIÓ, aunque ahora esté en otra página. Va FUERA del elif: no es
                    # una cara alternativa de la tarea, es historia suya, y compone con cualquiera de las de
                    # arriba. Medido en `find-theatre-tickets__es` (12:39): el detector de muro disparó de
                    # verdad, el worker se re-enrutó —correcto— y el hecho se borró con el siguiente `update_view`,
                    # así que zaelar pasó diez turnos diciendo «sigue sin dar señal de dónde está».
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
                lines.append(
                    _head + f" {_has_results} YA HA ENCONTRADO algo: no está bloqueada ni esperando. CUÉNTASELO "
                    "en este turno —QUÉ ha encontrado, con nombre y precio, no que «ya casi está»— y pregunta "
                    "si le vale o quiere que siga afinando. NO digas que «lo tiene en pantalla» ni «en la "
                    "hoja»: eso es otra cosa y puede tardar unos segundos más en escribirse; di lo que hay, "
                    "que es lo que sabes. Decirle que está parada teniendo datos delante es la "
                    "misma mentira que decirle que sigue buscando cuando ya no busca." + _shared + _walls_note)
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
                    _head + " Esa tarea sigue viva y te dará el resultado sola. Si el operador "
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
                    _t += " terminó CON resultado" if _f.get("has_results") else " terminó SIN traer nada"
                if _f.get("last_event"):
                    _t += f" (lo último que vio: {_f['last_event'][:90]})"
                _fb.append(_t)
            lines.append(
                "NAVEGADOR — YA TERMINADO: " + "; ".join(_fb) + ". Eso YA NO está en marcha: si el operador "
                "pregunta, dilo —terminó, y con qué— y ofrece el siguiente paso; decir que «sigue procesando» "
                "es contar algo que el sistema da por acabado. Y si lo último que vio responde a lo que te "
                "pidió (un teléfono, un horario, que solo se reserva llamando), DÁSELO: es el resultado, "
                "aunque no sea el que esperabas.")
        if _nt.login_waiting_id():
            lines.append("HAY UN INICIO DE SESIÓN PENDIENTE en el navegador (le abriste una ventana para entrar): "
                         "si el operador dice que ya inició sesión / 'ya estoy dentro', llama a login_done.")
    except Exception:
        pass
    return lines
