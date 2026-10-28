"""The BROWSER block of the live state (V2-276): what each live browser task is doing, and its rows.

Node 4.21 (`test_every_face_is_reachable`) requires each face (pending question · has results · waiting for login ·
blocked · healthy) to be reachable. Moved from `nucleo/flash/live_blocks.py` (refactor2710-08b).
"""
from __future__ import annotations

from nucleo.turn.prompt import live_browser_nav as _lbn
from nucleo.turn.prompt import live_sheet as _ls   # read through the module: a patch on live_sheet governs it


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
                    _rows_f = _ls._sheet_top_rows(_f.get("id") or "", 3)
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


def any_live_task_rows(n: int = 3) -> tuple[str, list[str]]:
    """`(goal, rows)` — the top NAMED rows of a live task whose sheet already has them, plus that task's goal.
    The reader the delivery backstop (V2-305, `delivery.sheet_delivery_backstop`) needs: same source as the face
    (`_sheet_top_rows`), so the backstop can never announce rows the prompt itself would not carry; the GOAL
    travels with them because the backstop's freshness test excludes the errand's own words (the category noun
    is in every turn by definition).

    WHICH task, when several have rows (audit V2-783 P1-2): the one whose card the previous turn acted on —
    the card he is looking at — else the first, as before. Reading always the first put the rows of one errand
    in the reply about another («the result in another card», a judge family)."""
    found: list[tuple[str, list[str], list[str]]] = []      # (goal, rows, its card ids)
    try:
        from widgets.navegador import tasks as _nt
        from widgets.results import sheet_names as _sn
        for _tid, _g in _nt.active_summaries():
            rows = _ls._sheet_top_rows(_tid, n)
            if rows:
                found.append((str(_g or ""), [r.strip("«»") for r in rows],
                              [_sn.instance_id(c) for c in _ls.boxes_of_tab(_tid)]))
        # …and the errand's OWN sheet, the source the TAREAS DE FONDO block shows (V2-781 T528: no browser task,
        # rows on the sheet for 151 s, `rows: 0` on every waiting reply).
        from nucleo import dispatch as _disp
        from nucleo.flash import errand_sheet as _es
        from nucleo import surfaces as _sf
        for t in _disp.pending_summaries() or []:
            if _sf.opens_doc(str(t.get("surface") or "")):
                continue                    # a report's working rows are not its delivery (V2-781)
            sheet = str(t.get("sheet") or "")
            rows = _es.rows_of_sheet(sheet, n) if sheet else []
            if rows:
                found.append((str(t.get("request") or t.get("goal") or ""), [r.strip("«»") for r in rows],
                              [_sn.instance_id(sheet)]))
    except Exception:  # noqa: BLE001 — a backstop that cannot read stays out of the reply
        __import__("logging").getLogger("zaelar.flash").warning("any_live_task_rows failed", exc_info=True)
    if not found:
        return "", []
    if len(found) > 1:
        try:
            from nucleo import canvas_focus
            focus = canvas_focus.last_turn_card([c for _g, _r, cards in found for c in cards])
            for goal, rows, cards in found:
                if focus and focus in cards:
                    return goal, rows
        except Exception:  # noqa: BLE001 — no focus reading: the first, as before
            __import__("logging").getLogger("zaelar.flash").debug("focus not read", exc_info=True)
    return found[0][0], found[0][1]
