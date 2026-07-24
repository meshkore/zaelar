"""nucleo/flash/procs.py — puente FlashBrain → supervisor de procesos de widgets (V2-004 · T63).

La capa refleja puede conducir procesos de vida propia (widgets `backed` como el navegador) sin bloquear el
turno de voz. Este módulo es un **PUENTE FINO** a `widgets/supervisor.py` — NO duplica la supervisión (mailbox +
backoff + aislamiento + desactivación tras N fallos siguen viviendo en el host, arrancado en el lifespan del
server, en el MISMO loop que la voz). Aquí solo: encolar una orden al owner de un widget, y consultar su estado.
Encolar (no ejecutar en línea) preserva el invariante del `backed`: el owner es el ÚNICO escritor de su store.
"""
from __future__ import annotations


def is_backed(widget_id: str) -> bool:
    """¿Es `widget_id` un widget backed (con proceso propio supervisado)?"""
    try:
        from widgets import supervisor
        return supervisor.is_backed(widget_id)
    except Exception:
        return False


def dispatch(widget_id: str, action: str, payload: dict | None = None) -> bool:
    """Deja una orden en el BUZÓN del owner del widget (no bloquea el turno). Devuelve True si se encoló
    (widget backed y vivo), False si no (passive/no arrancado/desactivado). Best-effort: nunca lanza."""
    try:
        from widgets import supervisor
        return supervisor.enqueue(widget_id, (action or "").strip(), payload or {})
    except Exception:
        return False


def status(widget_id: str) -> dict:
    """Estado del proceso supervisado del widget: {backed, running, disabled, fails}."""
    try:
        from widgets import supervisor
        return supervisor.info(widget_id)
    except Exception:
        return {"backed": False, "running": False, "disabled": False, "fails": 0}


def running() -> list[str]:
    """Ids de widgets backed con owner vivo."""
    try:
        from widgets import supervisor
        return supervisor.running()
    except Exception:
        return []
