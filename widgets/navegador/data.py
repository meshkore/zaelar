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


def _task_view(t: dict) -> dict:
    """View for a TASK CARD: one task = one tab = one card. Mini-browser on top (capture of its tab) plus feed below
    (progress/question/results). Rendered by widget.js when kind == 'task'."""
    return {
        "kind": "task",
        "id": t.get("id", ""), "title": t.get("title", ""), "goal": t.get("goal", ""),
        "goal_summary": t.get("goal_summary", ""),
        "status": t.get("status", ""),
        "phase": t.get("phase", ""), "phase_active": t.get("phase_active", False),
        "awaiting_login": t.get("awaiting_login", False),
        "url": t.get("url", ""), "page_title": t.get("page_title", ""),
        "shot": f"shot-{t.get('id', '')}.png", "shot_rev": t.get("shot_rev", 0),
        "events": t.get("events", []),
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
        "results": t.get("results"),
    }


def view_data(q: str = "") -> dict:
    """Browser state. If `q` is an active TASK id, return its card view (mini-browser + feed). Otherwise return the
    MAIN tab state (browse_web): address bar + capture/YouTube. Never raises."""
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
    return ("The 'navegador' widget is a web browser inside zaelar. You can open any website (open), search Google "
            "(search), or play YouTube (youtube); back/forward/reload and page scrolling are safe. To navigate "
            "inside a website (click/type/submit forms), use click/type/press. The page appears as a live capture; "
            "YouTube plays embedded.")
