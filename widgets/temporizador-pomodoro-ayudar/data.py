#
# Pomodoro widget — backend. A classic Pomodoro timer to manage focus/break blocks: 25 min de concentración,
# 5 min de descanso corto y 15 min de descanso largo tras 4 pomodoros. Stdlib only, never raises.
#
# Storage model: we persist the SESSION, not a per-second countdown. `ends_at` (epoch) is the moment the current
# running phase finishes; the remaining seconds are derived from it (widget.js ticks the display locally — that's
# cosmetic, not polling). When paused we store the frozen `remaining`. The background tick() settles a phase that
# elapsed off-screen and writes the current state to central memory so a voice question ("¿cuánto queda del
# pomodoro?") answers with fresh data even if the card was never opened.
#
import time

from .. import store

WID = "temporizador-pomodoro-ayudar"

WORK = 25 * 60          # concentración
SHORT = 5 * 60          # descanso corto
LONG = 15 * 60          # descanso largo
LONG_EVERY = 4          # descanso largo tras cada 4 pomodoros de concentración

_LABELS = {"work": "Concentración", "short_break": "Descanso corto", "long_break": "Descanso largo"}
_DURATIONS = {"work": WORK, "short_break": SHORT, "long_break": LONG}


def _seed() -> dict:
    return {"phase": "work", "running": False, "ends_at": None,
            "remaining": WORK, "completed": 0, "cycle": 0}


def _duration(phase: str) -> int:
    return _DURATIONS.get(phase, WORK)


def _remaining_now(db: dict) -> int:
    """Seconds left in the current phase: derived from ends_at if running, else the frozen value."""
    if db.get("running") and db.get("ends_at"):
        return max(0, int(round(db["ends_at"] - time.time())))
    return max(0, int(db.get("remaining", _duration(db.get("phase", "work")))))


def _advance(db: dict) -> dict:
    """Move to the next phase. Leaving a CONCENTRACIÓN phase counts a completed pomodoro."""
    if db.get("phase") == "work":
        db["completed"] = int(db.get("completed", 0)) + 1
        db["cycle"] = int(db.get("cycle", 0)) + 1
        db["phase"] = "long_break" if db["cycle"] % LONG_EVERY == 0 else "short_break"
    else:
        db["phase"] = "work"
    db["running"] = False
    db["ends_at"] = None
    db["remaining"] = _duration(db["phase"])
    return db


def _pack(db: dict) -> dict:
    phase = db.get("phase", "work")
    return {
        "phase": phase,
        "phase_label": _LABELS.get(phase, "Concentración"),
        "running": bool(db.get("running")),
        "remaining": _remaining_now(db),
        "total": _duration(phase),
        "completed": int(db.get("completed", 0)),
        "cycle": int(db.get("cycle", 0)) % LONG_EVERY,
        "long_every": LONG_EVERY,
        "durations": {"work": WORK, "short_break": SHORT, "long_break": LONG},
    }


def view_data(q: str = "") -> dict:
    try:
        db = store.load(WID, _seed())
        # If a running phase already elapsed (card was closed), settle it so the view is truthful.
        if db.get("running") and db.get("ends_at") and db["ends_at"] <= time.time():
            _advance(db)
            store.save(WID, db)
        return _pack(db)
    except Exception:
        return {"error": "No he podido cargar el temporizador.", "phase": "work",
                "phase_label": "Concentración", "running": False, "remaining": WORK, "total": WORK,
                "completed": 0, "cycle": 0, "long_every": LONG_EVERY,
                "durations": {"work": WORK, "short_break": SHORT, "long_break": LONG}}


def apply_action(action: str, payload: dict | None = None) -> dict:
    payload = payload or {}
    try:
        db = store.load(WID, _seed())
        act = (action or "").strip().lower()
        if act == "start":
            rem = _remaining_now(db)
            if rem <= 0:
                rem = _duration(db.get("phase", "work"))
            db["running"] = True
            db["remaining"] = rem
            db["ends_at"] = time.time() + rem
        elif act == "pause":
            db["remaining"] = _remaining_now(db)
            db["running"] = False
            db["ends_at"] = None
        elif act == "reset":
            db["running"] = False
            db["ends_at"] = None
            db["remaining"] = _duration(db.get("phase", "work"))
        elif act == "skip":
            _advance(db)
        else:
            return _pack(db)
        store.save(WID, db)
        return _pack(db)
    except Exception:
        return view_data()


def tick(ctx=None) -> None:
    """Background cycle (every 30s): settle an elapsed phase off-screen and mirror state to central memory."""
    try:
        db = store.load(WID, _seed())
        if db.get("running") and db.get("ends_at") and db["ends_at"] <= time.time():
            _advance(db)
            store.save(WID, db)
        # Mirror to memory ONLY while running (something to ask about); a slot supersedes, never piles up.
        if ctx is not None and db.get("running"):
            rem = _remaining_now(db)
            label = _LABELS.get(db.get("phase", "work"), "Concentración")
            text = (f"Pomodoro en marcha: {label}, quedan {rem // 60} min {rem % 60:02d} s. "
                    f"Pomodoros completados hoy: {int(db.get('completed', 0))}.")
            ctx.remember(text, slot=f"{WID}:estado")
    except Exception:
        pass
