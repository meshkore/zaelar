"""Whether a request is WORK to commission, and what that work is (V2-778 F1, 2026-10-01).

Moved out of `nucleo/flash/router_guards.py`, which had grown past its size ceiling: the readers that decide a
request deserves a worker (`create_widget_request`, `escalate_goal_from_window`, `money_work_needs_a_browser`,
`too_thin_to_commission`, `nothing_running_for` and their helpers). The code is the SAME; every name it read from
`router_guards` is read through the module (`_rg.<name>`), so a caller or a test that patches
`router_guards.<name>` still governs it, and `router_guards` re-exports every function here under its old name.
Import these through `router_guards` — it is the module this one was cut from.
"""
from __future__ import annotations

from nucleo.flash import router_guards as _rg


def _topic_words(text: str) -> set[str]:
    """Content words with punctuation stripped and function/date words dropped — what two errands can be
    compared BY."""
    out = set()
    for w in _rg._content_words(text):
        w = w.strip(".,;:!?¿¡()«»\"'-—")
        if len(w) > 2 and w not in _rg._NON_TOPIC and w not in _rg._DATE_ONLY_WORDS:
            out.add(w)
    return out


def nothing_running_for(goal: str, running_goals) -> bool:
    """True when NOTHING among the live errands is about `goal` — so a promise about it has nothing behind it.

    The escalation backstop was gated on «is anything running?», and the question that decides is «is anything
    running FOR THIS?». Measured twice, in two different cases:

      · `book-hotel-night-known__es` (2026-08-20): «Resérvame una noche en el Hotel Palacio de la Merced» →
        «Me pongo con ello» → nothing escalated, because a worker from the PREVIOUS errand was still alive. The
        mechanism showed `status=cancelled url=ticketmaster.es` while zaelar said «la reserva sigue en marcha»
        for four turns. The judge called it «divergencia crítica de dominio».
      · `restaurant-tonight-madrid` (2026-08-19): the same shape from the other side — the operator asked about
        Casa Lucio and got answered about El Rey León.

    The gate's own reasoning was right and incomplete: with a live task «sigo con ello» IS honest and
    re-escalating WOULD run the same work twice — but only if the live task is about what was asked.

    CONSERVATIVE ON PURPOSE, in the direction the gate was protecting: this answers True only when it can tell,
    and «cannot tell» means False (behave exactly as before). So a goal too thin to judge, or any overlap at all
    with something already running, keeps today's conduct. Running one errand twice is a defect the operator pays
    for; being told «sigo con ello» about somebody else's errand is one he cannot even see.
    """
    mine = _rg._topic_words(goal)
    if len(mine) < 2:
        return False               # too thin to judge → do not act on a guess
    for other in (running_goals or []):
        theirs = _rg._topic_words(str(other or ""))
        if not theirs or (mine & theirs):
            return False           # an unreadable goal, or any real overlap → assume it is this one
    return True


def create_widget_request(text: str) -> str:
    """Just the CLAUSE of `text` that asks to build a widget, or "" if none does.

    V2-155, measured on `three-tasks-at-once`: the backstop that adds a missing widget task appended the WHOLE
    turn, and a turn that asks for three things carries the other two inside it. That mattered because the
    request then went through `dispatch.find_duplicate`, whose STRONGEST signal is «same destination widget»:

        _target_widget("…un informe sobre coches eléctricos… y móntame un widget de un juego…") -> 'results'
        _target_widget("Elaborar un informe detallado sobre coches eléctricos para ciudad…")     -> 'results'
        find_duplicate(whole turn, "code")  -> the REPORT's session       ← the game is swallowed
        find_duplicate(just the game, "code") -> None                     ← it would have been created

    So the third task was not lost by the model failing to ask for it: it was correctly detected, appended as a
    sentence that says «informe» in it, and deduplicated against the report it was supposed to run alongside.

    Splitting on clause separators and reusing `looks_like_create_widget` keeps this free of a second vocabulary
    — the predicate that decides WHETHER a turn asks for a widget is the same one that decides WHICH part does.
    Falls back to the whole text when no single clause matches but the text as a whole does, so a plain «móntame
    un widget de X» (no separators) behaves exactly as before.
    """
    text = (text or "").strip()
    if not text or not _rg.looks_like_create_widget(text):
        return ""
    for part in (p.strip(" ,;.!?") for p in _rg._CLAUSE_SPLIT_RE.split(text)):
        if part and _rg.looks_like_create_widget(part):
            return part
    return text


def escalate_goal_from_window(window, current_text: str = "", max_back: int = 6) -> str:
    """The operator's request that a promise refers to, which is NOT always in this turn's text.

    V2-132, measured on `find-theatre-tickets__es`: the task was described across TWO turns — «consígueme dos
    entradas para el musical de El Rey León» and then, after zaelar correctly asked for the missing data,
    «este sábado, la sesión de tarde». zaelar answered the second one with «dame un momento que lo miro» and
    called no tool at all. The promise backstop looked only at THIS turn's text, which on its own describes no
    task, so it could not fire — and the run became eight turns of narrating a search that never started.

    Returns the goal to escalate (this turn's text appended, since it carries the detail that completes it), or
    "" if nothing in the window describes a task that needs a worker. Same lookback shape as the window the
    brain already sees; the caller still gates on "no tool fired AND nothing is running".
    """
    if current_text and _rg._needs_real_work(current_text):
        return current_text
    # V2-147: `max_back` counts the operator's OWN turns, not window ENTRIES. It used to slice the raw window,
    # so every exchange cost two of the budget and three «¿alguna novedad?» were enough to push the request out
    # of reach. Measured on the run: the task was named in the first turn, `_needs_real_work` recognised it, and
    # the lookback simply could not see that far — the promise «dame un momento que lo miro» came back with no
    # goal and nothing escalated. Counting assistant turns against a budget meant for the operator's history
    # punishes a conversation for the very thing that makes it normal: asking how it is going.
    seen = 0
    for msg in reversed(list(window or [])):
        if (msg or {}).get("role") != "user":
            continue
        seen += 1
        if seen > max_back:
            break
        content = str((msg or {}).get("content") or "").strip()
        if content and _rg._needs_real_work(content):
            return f"{content} — {current_text}".strip(" —") if current_text else content
    return ""


def money_work_needs_a_browser(text: str) -> bool:
    """A money / commitment errand that has to happen on a WEBSITE, so the worker must get a browser.

    V2-148 — every payment classified `generic`, measured on the case's own sentences: «paga la factura de la
    luz», «paga la factura de Endesa», «paga la factura de la luz en la web de Endesa» — all of them a worker
    with NO browser, even after the operator named the provider and said where he pays it.

    I had left this open TWICE (V2-141, V2-144) with the note «the destination of a payment is the provider's
    specific site, not a common trusted one, so it is not the same solution as a catalog category». That was
    right and it was also the wrong conclusion: it does not need a catalog entry AT ALL, it needs a BROWSER —
    the destination is whatever provider the operator names, and finding it is the worker's job.

    And the damage is not «it does not pay» (impossible without a real account, and the case does not penalise
    it): without a browser the task cannot reach the login wall, so the system loses the only honest answer it
    had — «llego al login de Endesa y necesito que entres tú» — and the turn fills the gap by narrating. That
    is literally the argument V2-126 wrote down for Netflix and V2-138 repeated for the rest of the providers.

    Carve-outs are the ones that already resolve inside the turn, plus a data-op on the operator's own lists:
    «borra la factura de la agenda» carries a money word and is a widget mutation, not an errand.
    """
    if not _rg._needs_real_work(text):
        return False
    try:
        from nucleo import danger as _danger
        if not (_danger.moves_money(text) or _danger.ends_a_commitment(text)):
            return False           # a marketplace/report errand routes by its own branch, not through here
    except Exception:
        return False
    return not _rg._DATA_OP_RE.search(_rg._norm_txt(text))


def _needs_real_work(text: str) -> bool:
    """Does this request need a worker, i.e. something happening OUTSIDE the conversation?

    V2-143 — `renew-gym-membership__es` measured the gap: «Renueva mi cuota del gimnasio de este mes» is not a
    marketplace, not a report and not a transactional category of the site catalog, so `looks_like_escalate_task`
    said no. Then the operator gave the missing datum, zaelar said «ahora me pongo con ello — busco los gimnasios
    de Sevilla», and NOTHING fired: 0 searches, 0 browser tasks. The signal that would have caught it was already
    in the tree and unused — `danger.moves_money` returns True for that exact sentence.

    SPENDING MONEY is real-world work by definition: no membership was ever renewed by talking. Show/close are
    excluded because they are resolved in the turn itself (V2-017) and «pon la factura en pantalla» would
    otherwise look like a money task.
    """
    if _rg.looks_like_escalate_task(text):
        return True
    try:
        from nucleo import danger as _danger
        # V2-138: ending a standing commitment is real-world work too, and it costs nothing — «cancela mi
        # suscripción a Netflix» is not money, so `moves_money` said no and the promise backstop could not fire
        # for the whole cancel family. `is_dangerous` would be too wide (it is also True for «borra el widget
        # de música», resolved inside the turn); `ends_a_commitment` is exactly the right width, measured on
        # both classes.
        if not (_danger.moves_money(text) or _danger.ends_a_commitment(text)):
            return False
    except Exception:
        return False
    # …and neither is putting something ON THE SCREEN. «pon la factura en pantalla» carries a money word and no
    # show VERB (`pon` is deliberately out of that list — it collides with «pon música»), so the screen has to
    # be named explicitly here.
    if _rg._SCREEN_TARGET_RE.search(_rg._norm_txt(text)):
        return False
    return not (_rg.is_pure_show_request(text) or _rg.looks_like_close(text) or _rg.looks_like_create_widget(text))


def too_thin_to_commission(text: str) -> bool:
    """True when `text` is a fragment that cannot commission a Brain Worker — 1–3 words with no directive.

    «Directive» is read structurally, from the verb lists the guards already keep: task verbs, show/activate/
    change verbs, close orders, login intent, search/navigation verbs, research verbs, the English directives
    with no Spanish-guarded equivalent («open/show/close/…»), and the single words that are also orders
    (`segmenter._ALSO_A_VERB`: «para», «sigue», «pon»…). A question («¿…?») always directs, and so does
    anything `_needs_real_work` recognises (marketplace/report errands, money, commitments).
    """
    raw = (text or "").strip()
    if not raw:
        return False                      # nothing to judge → behave as before
    if "?" in raw or "¿" in raw:
        return False                      # a question directs, however short
    n = _rg._norm_txt(raw)
    if len(n.split()) > 3:
        return False
    if _rg._needs_real_work(raw):
        return False
    if _rg._TASK_VERB_RE.search(n):
        return False
    if _rg._SHOW_VERB_RE.search(n) or _rg._ACTIVATE_VERB_RE.search(n) or _rg._CHANGE_VERB_RE.search(n):
        return False
    if _rg._LOGIN_INTENT_RE.search(n):
        return False
    if _rg._MKT_VERB_RE.search(n) or _rg._REPORT_RE.search(n) or _rg._RESEARCH_VERB_RE.search(n):
        return False
    if _rg._EN_DIRECTIVE_RE.search(n):
        return False
    if _rg.looks_like_close(raw):
        return False                       # «cierra eso» is an order however short
    try:
        from nucleo.flash.segmenter import _ALSO_A_VERB as _ALSO_VERB
        if any(w in _ALSO_VERB for w in n.split()):
            return False                  # «para»/«sigue»/«pon» alone are orders, never fragments
    except Exception:
        pass
    return True
