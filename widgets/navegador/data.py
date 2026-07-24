#
# data.py — la CARA (solo-lectura) del widget "navegador". Es un widget "backed" (kind:"backed"): el estado lo
# escribe SOLO el backend vivo (owner.py, un Chromium headless), y las acciones NO se aplican aquí: el host las
# encola en el buzón del owner (widgets/supervisor.py) — por eso apply_action NO muta el store, solo existe como
# red de seguridad si el backend no está vivo. Este módulo es stdlib puro y NUNCA revienta (contrato de widget).
#
from .. import store

WID = "navegador"
_SEED = {
    "mode": "blank", "url": "", "title": "Navegador",
    "rev": 0, "loading": False, "error": "",
    "can_back": False, "can_forward": False, "youtube_id": "", "youtube_title": "",
}


def _task_view(t: dict) -> dict:
    """Vista de una TARJETA DE TAREA (una tarea = una pestaña = una tarjeta): mini-navegador arriba (captura de SU
    pestaña) + feed abajo (progreso/pregunta/resultados). La pinta widget.js cuando kind == 'task'."""
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
        "results": t.get("results"),
    }


def view_data(q: str = "") -> dict:
    """Estado del navegador. Si `q` es el id de una TAREA activa → vista de su tarjeta (mini-navegador + feed).
    Si no, el estado del tab PRINCIPAL (browse_web): barra de direcciones + captura/YouTube. Nunca lanza."""
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
    """Red de seguridad: en un widget backed las acciones las encola el host en el buzón del owner ANTES de
    llegar aquí (widgets/server_api._route_backed). Si caemos aquí es que el backend no está vivo → informa sin
    tocar nada. No escribimos el store (el owner es el único escritor)."""
    data = view_data()
    if action in ("open", "search", "youtube", "back", "forward", "reload", "scroll", "click", "type", "press"):
        return {**data, "error": "El navegador no está activo ahora mismo. Reinténtalo en un momento."}
    return data


def coach_context() -> str:
    return ("El widget 'navegador' es un navegador web dentro de zaelar. Puedes abrir cualquier web (open), "
            "buscar en Google (search) o reproducir YouTube (youtube); atrás/adelante/recargar y desplazar la "
            "página son seguros. Para navegar por DENTRO de una web (clic/escribir/enviar formularios) usa "
            "click/type/press. La página se ve como una captura en vivo; YouTube se reproduce embebido.")
