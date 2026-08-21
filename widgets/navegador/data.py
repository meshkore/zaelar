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
        # V2-207 — los MUROS que esta tarea se comió. `active_progress()` los construye desde V2-176 y son lo que
        # llega al prompt, pero esta vista no los exponía, así que desde fuera del proceso «el muro no se anotó»
        # y «se anotó y el turno lo ignoró» se veían IDÉNTICOS. Son diagnósticos opuestos —uno es de la anotación
        # y el otro del turno— y decidir cuál se ataca costaba una ronda entera de medición. `wall` es el de la
        # página ACTUAL (se recalcula en cada captura) y `walls`/`last_wall` la historia, que es la que sobrevive
        # al re-enrutado: la distinción es justo la que V2-176 existe para mantener.
        "wall": t.get("wall", ""),
        "walls_hit": len(t.get("walls") or []),
        "last_wall": ((t.get("walls") or [{}])[-1] if t.get("walls") else {}),
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
