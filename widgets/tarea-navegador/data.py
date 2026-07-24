#
# data.py — panel de progreso para tareas del navegador.
# Muestra el navegador en miniatura (leyendo el store del widget navegador) y
# 10-12 líneas de estado de la tarea actual. El cerebro empuja las líneas
# mediante [[push:tarea-navegador]] o desde el propio navegador (owner.py).
# stdlib puro, nunca lanza.
#
from .. import store

WID = "tarea-navegador"
NAV = "navegador"

_SEED = {
    "title": "Navegador",
    "lines": [],
    "progress": "",
    "navegador_rev": 0,
}


def _read_navegador_data() -> dict:
    """Lee el store del navegador para obtener la captura y el estado actual.
    Devuelve datos mínimos: rev (para cache-busting de la imagen) y mode/title."""
    try:
        return store.load(NAV, {})
    except Exception:
        return {}


def view_data(q: str = "") -> dict:
    """Estado del panel de tareas. Combina el progreso propio con la
    información del navegador para mostrar la miniatura arriba."""
    out = dict(_SEED)
    try:
        db = store.load(WID, dict(_SEED))
        out.update(db)
    except Exception:
        pass
    # Añadir datos del navegador (solo lo que necesita el widget)
    nav = _read_navegador_data()
    out["navegador_mode"] = nav.get("mode", "blank")
    out["navegador_rev"] = nav.get("rev", 0)
    out["navegador_loading"] = nav.get("loading", False)
    out["navegador_title"] = nav.get("title", "")
    out["navegador_url"] = nav.get("url", "")
    out["navegador_error"] = nav.get("error", "")
    return out


def apply_action(action: str, payload: dict | None = None) -> dict:
    """Acciones del panel de progreso: push_lines, set_title, set_progress, clear."""
    p = payload or {}
    db = dict(_SEED)
    try:
        db = store.load(WID, dict(_SEED))
    except Exception:
        pass
    lines = db.get("lines", [])
    if isinstance(lines, list):
        lines = list(lines)
    else:
        lines = []

    if action == "push_lines":
        new_lines = p.get("lines", [])
        if isinstance(new_lines, list) and new_lines:
            lines.extend(new_lines)
            # Mantener máximo 15 líneas (cortar las más antiguas)
            if len(lines) > 15:
                lines = lines[-15:]
        db["lines"] = lines

    elif action == "set_title":
        title = str(p.get("title", "")).strip()
        if title:
            db["title"] = title

    elif action == "set_progress":
        pr = str(p.get("progress", "")).strip()
        if pr:
            db["progress"] = pr

    elif action == "clear":
        db["title"] = _SEED["title"]
        db["lines"] = []
        db["progress"] = ""

    store.save(WID, db)
    return view_data()


def coach_context() -> str:
    return ("El widget 'tarea-navegador' es un panel lateral angosto que muestra "
            "el progreso de las tareas automáticas del navegador (búsquedas, "
            "automatizaciones web). Se actualiza empujando líneas con push_lines "
            "o limpiando con clear. El título cambia con set_title.")
