#
# Gestiona-mensaje-recibido widget — backend. Un único mensaje de WhatsApp recibido de Gonza que hay que
# gestionar: marcarlo como atendido o responderle. El estado (pendiente/procesado/respondido) vive en el store
# propio del widget y refleja SIEMPRE la última acción real ejecutada (nunca un "hecho" sin haber mutado el dato).
#
import time

from .. import store

WIDGET_ID = "gestiona-mensaje-recibido"
_STATUSES = ("pendiente", "procesado", "respondido")


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M")


def _seed() -> dict:
    return {
        "sender": "Gonza",
        "platform": "whatsapp",
        "text": "Oye, ¿te va bien que quedemos mañana a las 19:00 para lo del proyecto? Dime algo cuando puedas.",
        "received_at": _now(),
        "status": "pendiente",
        "reply_text": None,
        "action_at": None,
        "log": [],
    }


def load_db() -> dict:
    db = store.load(WIDGET_ID, _seed())
    if db.get("status") not in _STATUSES:
        db["status"] = "pendiente"
    db.setdefault("reply_text", None)
    db.setdefault("action_at", None)
    db.setdefault("log", [])
    return db


def view_data(q: str = "") -> dict:
    db = load_db()
    return {
        "sender": db.get("sender", "Gonza"),
        "platform": db.get("platform", "whatsapp"),
        "text": db.get("text", ""),
        "received_at": db.get("received_at", ""),
        "status": db.get("status", "pendiente"),
        "reply_text": db.get("reply_text"),
        "action_at": db.get("action_at"),
        "log": db.get("log", [])[-5:],
    }


def _record(db: dict, action: str, extra: dict | None = None) -> None:
    entry = {"action": action, "at": _now()}
    if extra:
        entry.update(extra)
    db.setdefault("log", []).append(entry)
    db["action_at"] = entry["at"]


def apply_action(action: str, payload: dict | None = None) -> dict:
    payload = payload or {}
    db = load_db()

    if action == "process":
        db["status"] = "procesado"
        _record(db, "process")
        store.save(WIDGET_ID, db)

    elif action == "reply":
        text = (payload.get("text") or "").strip()
        if text:
            db["status"] = "respondido"
            db["reply_text"] = text
            _record(db, "reply", {"text": text})
            store.save(WIDGET_ID, db)

    elif action == "reopen":
        db["status"] = "pendiente"
        db["reply_text"] = None
        _record(db, "reopen")
        store.save(WIDGET_ID, db)

    return view_data()
