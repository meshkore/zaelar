#
# Cita con el Dentista — data layer. Un ÚNICO compromiso reservado (título/fecha/hora/estado) en el store
# aislado del widget (widgets/_data/reserva-cita-dentista/state.json). La cita REAL vive en la agenda
# (widgets/agenda, add_meeting) — este widget es la tarjeta de reserva/confirmación de ESE trámite concreto;
# la composición (poner la cita también en la agenda) la hace el cerebro llamando a los dos widgets, nunca
# este data.py a otro (aislamiento — ver widgets/AGENTS.md).
#
import re
import time
import unicodedata

from .. import store

WIDGET_ID = "reserva-cita-dentista"
DEFAULT_TITLE = "Dentista"


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c))


def _today() -> str:
    return time.strftime("%Y-%m-%d")


_WEEKDAYS = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4, "sabado": 5, "domingo": 6}


def _resolve_date(raw: str) -> str:
    """'mañana' / 'hoy' / 'pasado mañana' / 'el viernes' / ya 'YYYY-MM-DD' -> 'YYYY-MM-DD'."""
    s = (raw or "").strip().lower()
    if not s:
        return _today()
    if len(s) >= 8 and s[:4].isdigit() and "-" in s:
        return s[:10]
    n = _strip_accents(s)
    today = time.localtime()
    base = time.mktime(today)
    day = 86400
    if "pasado manana" in n:
        return time.strftime("%Y-%m-%d", time.localtime(base + 2 * day))
    if "manana" in n:
        return time.strftime("%Y-%m-%d", time.localtime(base + day))
    if "hoy" in n:
        return _today()
    for name, wd in _WEEKDAYS.items():
        if name in n:
            delta = (wd - today.tm_wday) % 7
            delta = delta or 7
            return time.strftime("%Y-%m-%d", time.localtime(base + delta * day))
    return _today()


def _resolve_time(raw: str, default: str = "17:00") -> str:
    """'cinco' / '5 de la tarde' / '17h' / '17:00' -> 'HH:MM'."""
    s = (raw or "").strip().lower()
    if not s:
        return default
    m = re.search(r"(\d{1,2})[:h\.](\d{2})", s)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    m = re.search(r"\b(\d{1,2})\b", s)
    if m:
        h = int(m.group(1))
        pm = any(w in s for w in ("tarde", "noche", "pm"))
        am = any(w in s for w in ("manana", "mañana", "madrugada", "am"))
        if pm and h < 12:
            h += 12
        elif not am and 1 <= h <= 7:
            h += 12
        return f"{h % 24:02d}:00"
    return default


def _seed() -> dict:
    return {"title": DEFAULT_TITLE, "date": "", "time": "", "status": "none"}


def view_data(q: str = "") -> dict:
    db = store.load(WIDGET_ID, _seed())
    return {
        "title": db.get("title") or DEFAULT_TITLE,
        "date": db.get("date", ""),
        "time": db.get("time", ""),
        "status": db.get("status", "none"),
        "now": _today(),
    }


def apply_action(action: str, payload: dict | None = None) -> dict:
    payload = payload or {}
    db = store.load(WIDGET_ID, _seed())

    if action == "reservar":
        db["title"] = payload.get("title") or db.get("title") or DEFAULT_TITLE
        db["date"] = _resolve_date(payload.get("date", ""))
        db["time"] = _resolve_time(payload.get("time", ""))
        db["status"] = "confirmed"
    elif action == "cancelar":
        db["status"] = "cancelled"

    store.save(WIDGET_ID, db)
    return view_data()
