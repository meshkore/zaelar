"""The browser task's sheet, read for the live state: has it rows, is its driver gone, its top rows, its site's name.

Moved from `nucleo/flash/live_blocks.py` (refactor2710-08b), with the faces documented where they are applied.
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


# V2-358 — a step the WORKER writes about the SCREEN is its claim, not our fact: «10 proposals on the results sheet» was
# painted beside verified lines while the sheet ended with 0 rows. Not dropped — MARKED, and only when the step names
# the screen and the sheet is empty. The forms are OUR vocabulary for our own sheet, never an outside site's.
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
        # V2-479/374 — what stays out is COUNTED: five rows were too few (14 cameras arrived as four accessories; 12 hotels
        # showed only the dear ones), and «there are N more» is not showing them. The order is the DOM's, faithfully;
        # the model cannot choose among what it does not see (V2-330). ~100 chars per row at worst.
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
