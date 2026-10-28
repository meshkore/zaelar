"""What the browser extracted goes to the results sheet AND to the conversation (`_hand_over`), with the note
it pushes for each page.
Moved out of `act_api.py`; every module name is read through the package (`_f.<name>`), so a patch on `act_api`
still governs every call.
"""

from widgets.navegador import act_api as _f


def _sheet_of(task_id: str) -> str:
    """The sheet for the task this tab belongs to (V2-259). Fail-soft to "" = the default sheet.

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
        fresh, repeated = _f.dedupe_by_url(items)
        named, unnamed = _f.by_identity(fresh)
        # V2-295 — named rows with an AMOUNT before named rows with nothing. See `by_amount`: `head` offered the
        # first three in DOM order, which is where rows whose price failed to render ended up.
        priced, hollow = _f.by_amount(named)
        named = priced + hollow
        ordered = named + unnamed          # rows WITH identity go first; nothing is discarded
        sig = "|".join(f"{(i or {}).get('title', '')}~{(i or {}).get('price', '')}~{(i or {}).get('tel', '')}"
                       for i in ordered[:5])
        if _f._HANDED.get(task_id) == sig:      # re-extracting the same page is not a new finding
            return
        _f._HANDED[task_id] = sig
        from widgets.navegador import tasks as _t
        prev = (_t.get(task_id) or {}).get("results") or {}
        # El HECHO se queda en la tarea: `has_results` es lo que deja al turno decir «ya trajo algo» en vez de
        # elegir entre «sigue viva» y «está bloqueada» (V2-192/V2-200). Lo que cambia en V2-257 es que la tarjeta
        # ya no lo PINTA — el hecho no es una superficie.
        _t.set_results(task_id, {"conclusion": (prev or {}).get("conclusion") or "", "items": ordered[:5]})
        # …y los HALLAZGOS van a la hoja, que es donde el operador los está esperando desde que se abrió sola al
        # encargar. Una sola puerta para los tres caminos (V2-257).
        own_sheet = _f._sheet_of(task_id)
        try:
            from widgets.results import intake as _intake
            _intake.push(ordered, sheet=own_sheet,
                         source_url=str((_t.get(task_id) or {}).get("url") or ""))
        except Exception:  # noqa: BLE001
            pass
        # V2-377 — un hallazgo SIN ENCARGO no puede presentarse como si fuera del que se está atendiendo.
        # Medido en `best-plumber-same-day__es` (2026-08-27, 2/5): mientras el operador pedía un fontanero de
        # urgencias, llegaron por esta puerta notas que decían «El navegador ha SACADO esto de la página,
        # trabajando en «la tarea del navegador»: Audi A3 2004 — 1500 €» y, más tarde, un SEAT León. Eran de
        # la búsqueda de coches ANTERIOR, cuya pestaña seguía viva sobre autoscout24. El turno los ofreció
        # como fontaneros DOS veces —«Perdona, yo no he pedido coches ni de coña jajaja»— y el juez lo archivó
        # como que zaelar ignoraba el prompt. No lo ignoraba: le dimos coches etiquetados como hallazgos.
        #
        # «La tarea del navegador» se lee como LA tarea, o sea la de ahora, y ahí está el daño: un relleno
        # nuestro afirmando una pertenencia que nadie comprobó. Es la tercera vez en la tanda que una frase
        # enlatada nuestra es la que miente (V2-176 «Hecho.», V2-209 «Aquí lo tienes»).
        goal = str((_t.get(task_id) or {}).get("goal") or "").strip()[:70]
        if not goal:
            # A tab opened through `nav_cli` by an errand that is not `kind=web` is named after the TASK and has no
            # goal of its own; its errand does (demo pass 75: 12 «tab of unknown errand» notes in one pass).
            try:
                from nucleo import dispatch as _disp
                goal = _disp.errand_goal_for_nav_task(task_id)[:70]
            except Exception:  # noqa: BLE001 — no dispatcher = a tab with no errand, which is the branch below
                goal = ""
        _sin_encargo = not goal
        if goal and own_sheet and named:
            # THE SHEET IS THE SURFACE (demo pass 75, 2026-10-03). V2-223 pushed every page to the voice turn
            # because back then the rows reached NOBODY; since V2-257 they land in the errand's own sheet, live,
            # and the errand's end report speaks for it. Pushing each page as «NAME IT THIS TURN» on top of that
            # made a background errand narrate monitors in the middle of the calendar (twelve notes in one pass;
            # «tidy up the screen» answered with «I'd close the extra tabs»). NAMED rows only: an empty page is news
            # about the errand being stuck (V2-370) and still reaches the voice; so do rows with no sheet to land in,
            # and a tab no errand owns.
            return

        body = _f._note_body(task_id, goal, _sin_encargo, items, ordered, named, unnamed, repeated, priced, hollow)
        from voice import brain_notes
        brain_notes.push("[SISTEMA] " + body)
    except Exception:  # noqa: BLE001
        pass


def _note_body(task_id: str, goal: str, _sin_encargo: bool, items: list, ordered: list, named: list,
               unnamed: list, repeated: int, priced: list, hollow: list) -> str:
    """The system note `_hand_over` pushes for one extracted page: its head rows, what was left out, the
    tally of the harvest, and the one order that fits — a tab no errand owns, named rows, an empty page after
    a delivery, or an empty page while still searching."""
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
    # Information that more existed is NEVER lost SILENTLY (the doctrine of `observability/evidence.py`).
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
    if _sin_encargo:
        # Se dice el HECHO y se nombra el hueco (V2-127/V2-133), en vez de rellenarlo con una etiqueta que
        # suena a «lo tuyo». No se calla: el hallazgo puede ser justo lo que el operador pidió hace un rato,
        # y tirarlo sería V2-223 otra vez.
        body = (f"Una pestaña del navegador ha sacado esto: {listing}{tail}. OJO: esa pestaña NO dice a qué "
                f"encargo pertenece, así que puede ser de una búsqueda ANTERIOR y no de lo que el operador "
                f"te está pidiendo ahora. NO se lo ofrezcas como resultado de lo que ha pedido. Si encaja "
                f"con algo que pidió antes, nómbralo diciendo de dónde sale; si no encaja con nada, "
                f"cállatelo y sigue con lo suyo.")
    elif named:
        body = (f"El navegador ha SACADO esto de la página, trabajando en «{goal}»: {listing}{tail}. Nadie "
                f"más lo sabe: no está en la conversación hasta que tú lo digas, así que NO puedes decir "
                f"que no hay resultados ni que sigues buscando sin más. NÓMBRALO EN ESTE TURNO y, en la "
                f"misma frase, di si sirve: si responde a lo que pidió el operador, dáselo como resultado "
                f"con nombre, precio y enlace; si es otra cosa —un anuncio, un producto distinto—, nómbralo "
                f"igual y di por qué no sirve y qué haces ahora.")
    elif _f._sheet_already_named(task_id):
        # V2-370 — la MISMA página vacía, pero con el encargo YA entregado detrás. La rama de abajo se
        # escribió para una búsqueda EN CURSO y dice «esa página no está dando lo que pidió»; disparada
        # al final, después de haber entregado, convierte esa frase en el veredicto del encargo entero.
        # Medido en `search-buy-bicycle__es` (2026-08-27, la mejor ronda en días: resultado 4, mecanismo
        # 4, dos bicis reales entregadas): el último turno cerró con «La página esa no está trayendo lo
        # que pediste, así que la dejo» — casi palabra por palabra la nota. El juez lo marcó [alta] como
        # afirmación falsa, y lo era; pero no la dijo el modelo, la dijimos nosotros. El prompt de ese
        # turno llevaba las cinco filas con nombre y precio: no fue desobediencia, fue elegir entre dos
        # hechos ciertos, y el que traía imperativo era éste.
        body = (f"El navegador ha leído OTRA página trabajando en «{goal}» y de ÉSTA no ha salido ningún "
                f"resultado con nombre: solo enlaces de navegación de la propia web ({listing}{tail}). Es "
                f"una página que no aporta, NO el final de la búsqueda: este encargo YA tiene resultados "
                f"con nombre entregados antes. Si lo cuentas, dilo así —que esta página no ha añadido "
                f"nada nuevo— y NUNCA que «la página no está trayendo lo que pediste» ni que lo dejas: "
                f"eso contradice lo que ya le has dado y borra un resultado que sí existe.")
    else:
        # Ni una fila con nombre: lo que la página dio son enlaces de navegación, no resultados. Se dice
        # tal cual, con la salida delante, en vez de servirlos como si fueran hallazgos.
        body = (f"El navegador ha leído la página trabajando en «{goal}» y NO ha sacado ni un resultado con "
                f"nombre: solo enlaces de navegación de la propia web ({listing}{tail}). DÍSELO EN ESTE "
                f"TURNO con tus palabras —esa página no está dando lo que pidió— y di qué haces ahora; no "
                f"los ofrezcas como si fueran resultados ni digas que sigues buscando sin más.")
    return body


def _sheet_already_named(task_id: str) -> bool:
    """Does THIS task's sheet already contain any named result? (V2-370)

    Se pregunta a la HOJA y no al registro de la tarea a propósito: `has_results` solo existe si alguien llamó
    a `set_results`, y la hoja es la que el operador tiene delante — es la misma elección que hizo V2-299 en la
    cara de tarea terminada, y por el mismo motivo (allí la línea decía «SIN traer nada» con 21 filas dentro).

    Fail-soft a False, o sea a la redacción de siempre. Es la dirección conservadora: sin nada entregado esa
    redacción es CORRECTA, y lo que se está evitando aquí es un caso que solo existe cuando ya hay entrega. Al
    revés —callarse la página vacía por si acaso— dejaría al turno sin poder explicar por qué no llega nada.
    """
    try:
        _sheet = _f._sheet_of(task_id)
        if not _sheet:
            # Sin hoja PROPIA no hay encargo del que hablar. `_sheet_of` cae a "" y esa es la hoja PELADA, que
            # es compartida (V2-259): leerla aquí dejaría que la entrega de OTRO encargo callara el aviso de
            # éste. Lo cazó un test que ya existía —la hoja pelada acumulaba filas de casos anteriores dentro
            # de la misma suite— y es el mismo defecto en producción, solo que ahí no se ve.
            return False
        from widgets.results import data as _rd
        items = (_rd.view_data(_sheet) or {}).get("items") or []
        return any(str((it or {}).get("title") or "").strip() for it in items)
    except Exception:  # noqa: BLE001
        return False
