"""Documentation translated to English."""
import json

from . import db as _db

# Default state: no personal data yet (the memory agent seeds it / V2-003), and ENGLISH.
#
# This is the FOURTH place the language bootstrap contract lives, and it was the one out of step. The other
# translated implementation note
# translated implementation note
# (`mem_processor._render`). So a brand-new account, before the operator had said a single word, was already
# committed to writing their memory in Spanish. The product opens in English and switches to the operator's real
# language on their first sentence; the memory has to start from the same place as everything else.
_DEFAULT: dict = {
    "assistant_name": "Zaelar",
    "operator_name": None,
    # None = NOT YET CHOSEN, the same convention `mission`/`operator_name`/`location` already use here. It used to
    # be the literal "en", and that literal was a PIN nothing could move: no code in the tree ever writes this
    # field (the i18n lock persists `settings.stt_language`, not the state), and a non-empty value means the two
    # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    # tester grepped the Spanish word for a datum that was in the prompt in English.
    # Resolved at READ time (see `read`), so it reports the language the operator actually has configured instead
    # of a guess, which is what the "linguistic start-up" decision of 2026-07-10 asked for in the first place: the
    # memory starts where everything else starts. What that decision was against is a HARDCODED "es"; "en" turned
    # out to be the same mistake mirrored.
    "language": None,
    # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    "mission": None,
    "treatment": None,        # p.ej. "directo, sin narrar" | "elaborado"
    # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    "rules": [],
    "location": None,
    "recent": [],             # tareas/mensajes recientes (lista corta)
    "topics": [],             # temas hablados recientemente
    # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    "open_widgets": [],       # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    "recent_widgets": [],     # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    "widget_registry": [],

    "activity": [],           # translated implementation note
    "sessions": [],           # translated implementation note
    # translated implementation note
    "rails": [],              # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    "security": {},
}


def read() -> dict:
    """Documentation translated to English."""
    row = _db.get_db().query_one("SELECT data FROM state WHERE id=1")
    base = dict(_DEFAULT)
    if row is not None:
        try:
            base.update(json.loads(row["data"]))
        except Exception:
            pass
    if not base.get("language"):
        base["language"] = _active_language()
    return base


def _active_language() -> str:
    """Documentation translated to English."""
    try:
        from voice.engine.core import langs
        return langs.current_code()
    except Exception:  # noqa: BLE001
        return "en"


def write(data: dict) -> None:
    """Documentation translated to English."""
    merged = dict(_DEFAULT)
    merged.update(data or {})
    blob = json.dumps(merged, ensure_ascii=False)
    _db.get_db().execute(
        "INSERT INTO state (id, data) VALUES (1, ?) "
        "ON CONFLICT(id) DO UPDATE SET data=excluded.data",
        (blob,),
    )


import threading

_patch_lock = threading.Lock()


def patch(fields: dict) -> dict:
    """Documentation translated to English."""
    with _patch_lock:
        cur = read()
        cur.update(fields or {})
        write(cur)
        return cur


# translated implementation note
def security_flag(key: str, default=False):
    """Documentation translated to English."""
    try:
        return (read().get("security") or {}).get(key, default)
    except Exception:
        return default


def set_security_flag(key: str, value) -> None:
    """Documentation translated to English."""
    with _patch_lock:
        cur = read()
        sec = dict(cur.get("security") or {})
        sec[key] = value
        cur["security"] = sec
        write(cur)


# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
_REGISTRY_CAP = 200


def set_widget_registry(rows) -> list:
    """Documentation translated to English."""
    rows = list(rows or [])
    if len(rows) > _REGISTRY_CAP:
        rows = rows[:_REGISTRY_CAP] + [{"_truncated": True, "total": len(rows), "shown": _REGISTRY_CAP,
                                        "hint": "catálogo completo en GET /widgets"}]
    with _patch_lock:
        cur = read()
        cur["widget_registry"] = rows
        write(cur)
        return rows


# translated implementation note
_RECENT_CAP = 6


def push_recent_widgets(ids, cap: int = _RECENT_CAP) -> list:
    """Documentation translated to English."""
    if isinstance(ids, str):
        ids = [ids]
    fresh = []
    for w in (ids or []):
        b = str(w or "").split("::", 1)[0].strip().lower()
        if b and b not in fresh:
            fresh.append(b)
    if not fresh:
        return read().get("recent_widgets") or []
    with _patch_lock:
        cur = read()
        prev = [str(w).strip().lower() for w in (cur.get("recent_widgets") or []) if str(w).strip()]
        # translated implementation note
        merged = fresh + [w for w in prev if w not in fresh]
        merged = merged[:max(1, int(cap))]
        cur["recent_widgets"] = merged
        write(cur)
        return merged
