# The browser's STATE lines, in two blocks: reading each live browser task (its progress, its walls, a login it
# waits on, a sheet with results) and saying what the brain may claim about them (V2-778 F1, 2026-10-01).
#
# Moved out of `nucleo/flash/live_blocks.py::navegador_lines` (382 lines) with no behaviour change. Every name the
# blocks read from `live_blocks` is read through it (`_lb.<name>`), so a patch on `live_blocks` still governs them.
#
# (A comment, not a docstring: the prose ratchet counts this module's string constants as prompt text.)
from __future__ import annotations

from nucleo.flash import live_blocks as _lb


def read_the_browser_tasks(*, _asked, _bits, _blocked, _has_results, _hit_walls, _login, _orphan, _prog, act) -> dict:
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
                _b += f" — en {_lb._site_of(_p['url'])}"
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
            if _le and not (_le.startswith("🌐") and _lb._site_of(_le.split()[-1]) == _lb._site_of(_p.get("url") or "")):
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
            elif _p.get("has_results") or _lb._found_candidates(_tid):
                _b += " · YA HA ENCONTRADO ALGO"
                if not _has_results:
                    _has_results = _who
                    _rows = _lb._sheet_top_rows(_tid)
            # V2-310 — SIN CONDUCTOR gana a login/muro/atasco: si el worker murió, que el operador
            # entre en la web o que la página desbloquee no sirve de nada; nadie va a seguir. Pierde
            # contra `question` y `has_results`, que siguen siendo lo más útil que decir (y el hecho
            # se anota igual abajo, fuera del elif, para que la frase no mienta).
            elif _lb._driver_is_gone(_tid, _p):
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
            elif int(_p.get("stalled_s") or 0) >= _lb._STALLED_S and (_p.get("url") or _p.get("steps")):
                _b += f" · lleva {int(_p['stalled_s']) // 60} min SIN MOVERSE de esa página"
                _blocked = _blocked or _who
            # LOS MUROS QUE YA SE COMIÓ, aunque ahora esté en otra página. Va FUERA del elif: no es
            # una cara alternativa de la tarea, es historia suya, y compone con cualquiera de las de
            # arriba. Medido en `find-theatre-tickets__es` (12:39): el detector de muro disparó de
            # verdad, el worker se re-enrutó —correcto— y el hecho se borró con el siguiente `update_view`,
            # así que zaelar pasó diez turnos diciendo «sigue sin dar señal de dónde está».
            if not _orphan and _lb._driver_is_gone(_tid, _p):
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
    _out = locals()
    return {k: _out[k] for k in ('_asked', '_blocked', '_has_results', '_hit_walls', '_login', '_orphan', '_rows', ) if k in _out}


def say_the_browser_state(*, _asked, _blocked, _has_results, _head, _login, _orphan, _rows, _shared, _walls_note, lines) -> dict:
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
            # V2-443 — sin filas solo hay `kept`, que lo dice el WORKER: se marca, no se afirma.
            lines.append(
                _head + f" {_has_results} DICE QUE YA TIENE CANDIDATOS —es SU cuenta, no la hemos comprobado— y"
                " NO ha llegado ni una fila, así que no tienes ningún nombre. La tarea no está bloqueada ni"
                " esperando: sigue trabajando. Cuéntale eso y solo eso —que sigue en ello y que aún no ha"
                " llegado nada que puedas darle, y que se lo pasas en cuanto llegue—; si te pregunta qué tiene,"
                " di honestamente que todavía nada confirmado. Y OJO con la diferencia, que es toda la"
                " cuestión: «TODAVÍA NO HA LLEGADO nada» es cierto y puedes decirlo; «NO HA ENCONTRADO nada»"
                " es otra cosa, ESO NO LO SABES y no lo digas. NO te inventes nombres, NO prometas un detalle"
                " concreto y NO digas que ya tienes resultados ni que están en pantalla." + _shared + _walls_note)
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
    _out = locals()
    return {k: _out[k] for k in () if k in _out}
