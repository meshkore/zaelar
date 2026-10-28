"""What the browser extracted goes to the results sheet AND to the conversation (`_hand_over`), with the note
it pushes for each page. Names are read through the package (`_f.<name>`).
"""

from widgets.navegador import act_api as _f


def _sheet_of(task_id: str) -> str:
    """The sheet for the task this tab belongs to (V2-259). Fail-soft to "" = the default sheet.

    V2-281 — the TAB is asked first because it outlives the worker that opened it (a finding after the session
    record is gone would land in the bare sheet). The live-session registry stays as fallback for unstamped tabs.
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
    """What the browser EXTRACTED goes to the results sheet AND to the conversation, not only to the worker (V2-223).

    It travels as a PUSHED note, not a prompt line: pushed system notes are said in the next turn, prompt status
    lines are not. JUDGEMENT stays with the brain (the first extraction may be an ad): the note hands over the facts
    and names the test. V2-226 — the note is ONE order (name it this turn and, in the same sentence, say whether it
    serves); two orders in one sentence resolve by coin flip, and «no hay resultados» is banned outright.
    """
    if not items:
        return
    try:
        fresh, repeated = _f.dedupe_by_url(items)
        named, unnamed = _f.by_identity(fresh)
        # V2-295 — named rows with an AMOUNT before named rows with nothing (see `by_amount`).
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
        # The FACT stays on the task: `has_results` lets the turn say «it already brought something» (V2-192/V2-200);
        # the card no longer paints it (V2-257).
        _t.set_results(task_id, {"conclusion": (prev or {}).get("conclusion") or "", "items": ordered[:5]})
        # …and the FINDINGS go to the sheet the operator is waiting on. One door for the three paths (V2-257).
        own_sheet = _f._sheet_of(task_id)
        try:
            from widgets.results import intake as _intake
            _intake.push(ordered, sheet=own_sheet,
                         source_url=str((_t.get(task_id) or {}).get("url") or ""))
        except Exception:  # noqa: BLE001
            pass
        # V2-377 — a finding with NO errand must not be presented as the one being served: a stale tab from an
        # earlier search would be offered as the current errand's result. Canned fill that asserts ownership nobody
        # checked is a lie of ours; the no-errand branch of the note says so.
        goal = str((_t.get(task_id) or {}).get("goal") or "").strip()[:70]
        if not goal:
            # A tab opened through `nav_cli` by a non-`kind=web` errand is named after the TASK and has no goal of
            # its own; its errand does.
            try:
                from nucleo import dispatch as _disp
                goal = _disp.errand_goal_for_nav_task(task_id)[:70]
            except Exception:  # noqa: BLE001 — no dispatcher = a tab with no errand, which is the branch below
                goal = ""
        _sin_encargo = not goal
        if goal and own_sheet and named:
            # THE SHEET IS THE SURFACE: named rows already land live in the errand's own sheet (V2-257) and its end
            # report speaks for them, so they are not pushed to the voice too. An empty page (stuck errand, V2-370),
            # rows with no sheet to land in, and a tab no errand owns still reach the voice.
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
        # V2-240 — the PHONE travels with the row: on a service errand it is the datum that resolves.
        bits = [str(i.get("title") or "").strip()[:80], str(i.get("price") or "").strip()[:24],
                str(i.get("tel") or "").strip()[:24], str(i.get("url") or "").strip()[:120]]
        return " — ".join(b for b in bits if b)

    # The note's HEAD is the named rows; with none, what there is — so the turn can say «this page only gives
    # categories, switching site», which is useful and true.
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
    # THE HARVEST in numbers (V2-296): counted in ONE place, where both halves of each cut are alive, and guarded
    # against counting the same page twice by `_HANDED`.
    try:
        _t.tally(task_id, pages=1, rows=len(items), repeated=repeated, unnamed=len(unnamed),
                 hollow=len(hollow), kept=len(priced), offered=len(head))
    except Exception:  # noqa: BLE001
        pass
    if _sin_encargo:
        # State the FACT and name the gap (V2-127/V2-133) instead of filling it with a label that sounds like «yours».
        # Not silenced: it may be exactly what the operator asked for earlier.
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
        # V2-370 — the SAME empty page, but with the errand ALREADY delivered: the «not giving what you asked»
        # wording below is for a search in progress; fired after delivery it becomes the verdict of the whole errand.
        body = (f"El navegador ha leído OTRA página trabajando en «{goal}» y de ÉSTA no ha salido ningún "
                f"resultado con nombre: solo enlaces de navegación de la propia web ({listing}{tail}). Es "
                f"una página que no aporta, NO el final de la búsqueda: este encargo YA tiene resultados "
                f"con nombre entregados antes. Si lo cuentas, dilo así —que esta página no ha añadido "
                f"nada nuevo— y NUNCA que «la página no está trayendo lo que pediste» ni que lo dejas: "
                f"eso contradice lo que ya le has dado y borra un resultado que sí existe.")
    else:
        # No named row: the page gave navigation links, not results — said as such, with the way out in front.
        body = (f"El navegador ha leído la página trabajando en «{goal}» y NO ha sacado ni un resultado con "
                f"nombre: solo enlaces de navegación de la propia web ({listing}{tail}). DÍSELO EN ESTE "
                f"TURNO con tus palabras —esa página no está dando lo que pidió— y di qué haces ahora; no "
                f"los ofrezcas como si fueran resultados ni digas que sigues buscando sin más.")
    return body


def _sheet_already_named(task_id: str) -> bool:
    """Does THIS task's sheet already contain any named result? (V2-370)

    Asks the SHEET, not the task record: `has_results` exists only if someone called `set_results`, and the sheet
    is what the operator sees (same choice as V2-299). Fail-soft to False = the usual wording, the conservative way.
    """
    try:
        _sheet = _f._sheet_of(task_id)
        if not _sheet:
            # No sheet of its OWN: `_sheet_of` fell to "", the shared bare sheet (V2-259) — reading it would let
            # ANOTHER errand's delivery silence this one's warning.
            return False
        from widgets.results import data as _rd
        items = (_rd.view_data(_sheet) or {}).get("items") or []
        return any(str((it or {}).get("title") or "").strip() for it in items)
    except Exception:  # noqa: BLE001
        return False
