#
# data.py: read-only face of the "navegador" widget. It is a backed widget (kind:"backed"): state is written ONLY
# by the live backend (owner.py, a headless Chromium), and actions are NOT applied here. The host enqueues them in
# the owner's mailbox (widgets/supervisor.py), so apply_action does NOT mutate the store and only exists as a safety
# net when the backend is not alive. This module is pure stdlib and NEVER crashes, per widget contract.
#
from .. import store

WID = "navegador"
_SEED = {
    "mode": "blank", "url": "", "title": "Navegador",
    "rev": 0, "loading": False, "error": "",
    "can_back": False, "can_forward": False, "youtube_id": "", "youtube_title": "",
    # `updated` is written by the OWNER on every state save (owner.py); seeding it keeps view_data's SHAPE
    # identical whether the browser has run yet or not — the golden was captured from a live store and the
    # harness reads a fresh one, which is how `make test-widgets` sat red on a phantom drift (V2-601 T-10).
    "updated": "",
}


#: How many state lines the card shows. THREE, and the number is the point (V2-257): the card used to dump the
#: last SIXTEEN events under a results list, which is a log, not a state — the operator has to be able to read
#: "where is it now" at a glance. The full history is not lost: milestones go to observability with their trace
#: (`tasks.milestone`), which is where an audit belongs.
_STATE_LINES = 3


def _state(t: dict) -> list[str]:
    """The last few things that happened, newest LAST — what this browser is doing, in three lines.

    Deduplicated against the previous line for the same reason `dispatch.session_phase` does it: three identical
    lines look like progress without being any, and that is the exact lie this area keeps removing.
    """
    out: list[str] = []
    for ev in (t.get("events") or []):
        text = str((ev or {}).get("text") or "").strip()
        if text and (not out or out[-1] != text):
            out.append(text)
    return out[-_STATE_LINES:]


def _task_view(t: dict) -> dict:
    """View for a TASK CARD: one task = one tab = one card.

    V2-257 — this card is the MONITOR of one browser: the capture of its tab and a few lines saying what it is
    doing. It is NOT where findings are shown; those go to the `results` sheet, which is single per errand while
    browsers are N. So `results` is deliberately absent from this view even though the task record still carries
    it: the record keeps the FACT (`has_results`, which the prompt reads — V2-192/V2-200), the card stopped being
    a surface for it.
    """
    return {
        "kind": "task",
        # `title` drives the card's HEADER (`live_title` in the manifest): what is being searched for, not the
        # name of the piece. With several browsers open, all of them called «Navegador», the header identified
        # nothing at all.
        "id": t.get("id", ""),
        "title": (t.get("goal_summary") or t.get("title") or t.get("goal") or "").strip()[:70],
        "goal": t.get("goal", ""),
        "goal_summary": t.get("goal_summary", ""),
        "status": t.get("status", ""),
        "phase": t.get("phase", ""), "phase_active": t.get("phase_active", False),
        "awaiting_login": t.get("awaiting_login", False),
        "url": t.get("url", ""), "page_title": t.get("page_title", ""),
        "shot": f"shot-{t.get('id', '')}.png", "shot_rev": t.get("shot_rev", 0),
        "state": _state(t),
        "question": t.get("question", ""),
        # V2-207 — the WALLS this task got stuck on. `active_progress()` builds them from V2-176 and they are what
        # reaches the prompt, but this view did not expose them, so from outside the process “the wall was not
        # recorded” and “it was recorded and the turn ignored it” looked IDENTICAL. They are opposite diagnoses —
        # one concerns the recording and the other the turn—and deciding which one to address cost a whole round of
        # measurement. `wall` is the one for the CURRENT page (recomputed on every capture), while `walls`/`last_wall`
        # are the history, which survives rerouting: preserving that distinction is exactly what V2-176 exists for.
        "wall": t.get("wall", ""),
        "walls_hit": len(t.get("walls") or []),
        "last_wall": ((t.get("walls") or [{}])[-1] if t.get("walls") else {}),
        # WHICH SHEET this tab belongs to. Stamped at birth (V2-281) and, until now, readable only from inside
        # the process — so from outside, "the tab was never stamped" and "the tab is stamped and something
        # downstream ignored it" looked IDENTICAL. That matters because `nucleo/flash/live_blocks.py::
        # _sheet_has_rows` resolves the errand's sheet through this stamp: with no stamp it answers False no
        # matter how full the sheet is, and the turn goes on saying it has nothing while the operator watches
        # the rows land. Same reason `wall`/`walls_hit` were exposed by V2-207 — from outside the process, a
        # fact that was never recorded and a fact that was recorded and then dropped read the same, and picking
        # the wrong one costs a round of measuring the wrong half.
        "sheet": t.get("sheet", ""),
    }


def view_data(q: str = "") -> dict:
    """Browser state. If `q` is an active TASK id, return its MONITOR view (capture + state lines). Otherwise
    return the MAIN tab state (browse_web): address bar + capture/YouTube. Never raises."""
    q = (q or "").strip()
    if q:
        try:
            from . import tasks
            t = tasks.get(q)
            if t:
                return _task_view(t)
        except Exception:
            pass
    try:
        return store.load(WID, dict(_SEED))
    except Exception as e:
        return {**_SEED, "error": f"no data: {e}"}


def apply_action(action: str, payload: dict | None = None) -> dict:
    """Safety net: in a backed widget, actions are enqueued by the host into the owner's mailbox BEFORE reaching
    here (widgets/server_api._route_backed). If execution falls here, the backend is not alive, so report without
    touching anything. Do not write the store; the owner is the only writer."""
    data = view_data()
    if action in ("open", "search", "youtube", "back", "forward", "reload", "scroll", "click", "type", "press"):
        return {**data, "error": "El navegador no está activo ahora mismo. Reinténtalo en un momento."}
    return data


def coach_context() -> str:
    return ("The 'navegador' widget is a web browser inside zaelar. Its card is the MONITOR of what this browser "
            "is doing right now; findings are shown in the 'results' sheet, never here. "
            "You can open any website (open), search Google "
            "(search), or play YouTube (youtube); back/forward/reload and page scrolling are safe. To navigate "
            "inside a website (click/type/submit forms), use click/type/press. The page appears as a live capture; "
            "YouTube plays embedded.")


def card_face(instance: str = "") -> dict:
    """What THIS browser card SHOWS, and whether it is BLANK — read by `widgets/instances.py` (V2-605).

    Measured 2026-09-07, session `43b7bf79`. With a task tab on thefork.es and a second, blank browser card on
    the canvas, «ábreme el navegador» produced «Tienes 2 abiertas: ¿cuál te enseño, "t1" o "navegador"?» — five
    times, verbatim, while the operator answered it («uno está vacío y el otro tiene la web»), rephrased it, and
    finally gave up. The question named the INSTANCE SUFFIX and the BASE ID, which is what `instances._label`
    falls back to when a widget cannot name its own cards, and the module's own docstring already forbade it:
    *«"¿results::t1 o results::t2?" is not a question, it is a dump»*. Only `results` could ever answer, so the
    browser — the piece that has had instances the longest — dumped ids.

    A browser card is named by the PAGE IT IS ON, because that is the only thing the operator can see and
    therefore the only thing he can answer with. `blank` is the other half and it is what removes the question
    entirely here: a tab sitting on nothing is never the one somebody meant to be shown.
    """
    inst = str(instance or "").strip()
    try:
        view = view_data(inst) or {}
    except Exception:  # noqa: BLE001
        return {}
    url = str(view.get("url") or "").strip()
    # `about:blank` is a real URL that shows nothing — the state a freshly launched tab sits in, and exactly what
    # the second card held in the measured session. Treating it as content is how a blank card wins a question.
    blank = (not url) or url.startswith("about:blank") or str(view.get("mode") or "") == "blank"
    if blank:
        # A blank card has no page to be named after, and its stored title is the PIECE's name («Navegador»,
        # «Nuevo navegador») — which distinguishes nothing, the very failure this function exists to remove.
        # The resolver names a blank card as blank; that IS what the operator can see.
        return {"label": "", "blank": True}
    # THE HOST, not the page title. Measured while testing this very function: «Reserva en los mejores
    # restaurantes de España | TheFork» capped to a speakable length becomes «Reserva en los mejores restaurantes
    # de…» — it drops «TheFork», the only half that identifies anything, because a page title is marketing prose
    # with the site's name LAST. The operator names a browser card the way anybody does: «el otro tiene la web
    # del Tenedor». `www.` goes, since it distinguishes nothing and costs a syllable out loud.
    host = url.split("://", 1)[-1].split("/", 1)[0].strip()
    if host.startswith("www."):
        host = host[4:]
    # No host (a `file:`/`data:` tab, or a URL we cannot read): what the task is LOOKING FOR distinguishes it
    # just as well, and the page title is the last resort before giving up and letting the id fallback speak.
    label = host or str(view.get("title") or "").strip() or str(view.get("page_title") or "").strip()
    return {"label": label, "blank": False}
