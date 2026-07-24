"""
Timer/countdown widget — backend.
Persiste el temporizador en store para que sobreviva a refrescos.
El brain fija el tiempo con apply_action("set", {"seconds": N, "label": "..."}).
"""
from __future__ import annotations

import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from .. import store

WID = "timer"
DB_VERSION = 1


def _default() -> dict:
    return {
        "remaining": 0,
        "target_seconds": 0,
        "label": "",
        "running": False,
        "started_at": 0,
        "paused_at": 0,
        "_v": DB_VERSION,
    }


def _migrate(db: dict, from_v: int) -> dict:
    if from_v < 1:
        db.setdefault("running", False)
        db.setdefault("started_at", 0)
        db.setdefault("paused_at", 0)
    return db


def _load() -> dict:
    return store.load(WID, _default(), version=DB_VERSION, migrate=_migrate)


def _save(db: dict) -> None:
    store.save(WID, db)


def _compute_remaining(db: dict) -> int:
    """Calculate current remaining seconds based on running state."""
    if not db.get("target_seconds"):
        return 0
    if not db.get("running"):
        return max(0, db.get("remaining", 0))
    elapsed = time.time() - db.get("started_at", time.time())
    return max(0, db["target_seconds"] - int(elapsed))


def view_data(q: str = "") -> dict:
    """Return current timer state."""
    try:
        db = _load()
        remaining = _compute_remaining(db)
        # If running, update persisted remaining so we're consistent
        if db.get("running") and remaining != db.get("remaining"):
            db["remaining"] = remaining
            _save(db)
        return {
            "remaining": remaining,
            "target_seconds": db.get("target_seconds", 0),
            "label": db.get("label", ""),
            "running": db.get("running", False),
            "finished": remaining <= 0 and db.get("target_seconds", 0) > 0,
        }
    except Exception as e:
        return {"error": str(e)[:120], "remaining": 0, "running": False, "finished": False}


def apply_action(action: str, payload: dict) -> dict:
    """Actions:
    - "set": {"seconds": int, "label": str} — set a new timer (overrides)
    - "start": resume countdown
    - "pause": pause countdown
    - "reset": reset to 0 / cancel
    """
    try:
        db = _load()
        if action == "set":
            secs = max(0, int(payload.get("seconds", 0)))
            db["target_seconds"] = secs
            db["remaining"] = secs
            db["label"] = str(payload.get("label", ""))[:40]
            db["running"] = secs > 0
            db["started_at"] = time.time() if secs > 0 else 0
            db["paused_at"] = 0
            _save(db)
            return {"ok": True, "remaining": secs, "running": secs > 0}

        elif action == "start":
            remaining = _compute_remaining(db)
            if remaining > 0:
                db["running"] = True
                db["started_at"] = time.time() - (db["target_seconds"] - remaining)
                db["paused_at"] = 0
                _save(db)
            return {"ok": True, "remaining": remaining, "running": True}

        elif action == "pause":
            db["remaining"] = _compute_remaining(db)
            db["running"] = False
            db["paused_at"] = time.time()
            _save(db)
            return {"ok": True, "remaining": db["remaining"], "running": False}

        elif action == "reset":
            db["target_seconds"] = 0
            db["remaining"] = 0
            db["running"] = False
            db["started_at"] = 0
            db["paused_at"] = 0
            db["label"] = ""
            _save(db)
            return {"ok": True, "remaining": 0, "running": False}

        return {"ok": False, "error": f"unknown action '{action}'"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}
