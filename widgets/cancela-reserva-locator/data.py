#
# Cancelación de reserva por localizador — data layer. This widget is a MIRROR, not the actor: it tracks the
# real-world status of cancelling a reservation (e.g. an ITV appointment at Itevelesa) identified by its
# locator. The actual cancellation happens for real against the provider's own system (driven by the brain via
# a browser-automation worker, outside this widget — a widget never reaches out to a 3rd-party site to perform
# an irreversible real-world action); this data.py only stores/reflects that outcome so a voice query answers
# with the true state even if the card was never opened. `mark_cancelled`/`mark_failed` are how the brain
# writes the CONFIRMED real result back here once it has actually checked.
#
import os
import subprocess
import sys
import time

from .. import store

WIDGET_ID = "cancela-reserva-locator"
DB_VERSION = 1

STATUS_PENDING = "pendiente_cancelacion"
STATUS_CANCELLED = "cancelada"
STATUS_ERROR = "error"


def _open_in_system_viewer(path: str) -> bool:
    # Opens the file in the OS's own default viewer app (Preview, Photos, whatever is set) —
    # never inline in the widget itself, so the operator sees the REAL captured proof.
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", path])
        elif sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception:
        return False


def _seed() -> dict:
    # Seeded with the reservation that prompted this widget, so it is visible right away while the brain
    # works the real cancellation in the background.
    now = time.strftime("%Y-%m-%d %H:%M")
    return {
        "reservations": [
            {
                "locator": "38179633",
                "provider": "Itevelesa",
                "note": "Cita ITV de Rickard, confirmada para las 10:00",
                "date": "2026-07-23",
                "status": STATUS_CANCELLED,
                "reason": "",
                "created_at": now,
                "updated_at": now,
            }
        ]
    }


def _migrate(db: dict, from_v: int) -> dict:
    return db


def _load() -> dict:
    return store.load(WIDGET_ID, _seed(), version=DB_VERSION, migrate=_migrate)


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M")


def _find(db: dict, locator: str) -> dict | None:
    for r in db.get("reservations", []):
        if r.get("locator") == locator:
            return r
    return None


def view_data(q: str = "") -> dict:
    db = _load()
    items = sorted(
        db.get("reservations", []),
        key=lambda r: r.get("updated_at") or r.get("created_at") or "",
        reverse=True,
    )
    pending = sum(1 for r in items if r.get("status") == STATUS_PENDING)
    return {"reservations": items, "pending": pending}


def ref_index() -> list[dict]:
    db = _load()
    return [
        {
            "id": r.get("locator", ""),
            "label": f"{r.get('provider', '')} {r.get('locator', '')}".strip(),
            "field": "locator",
            "hint": r.get("note", ""),
        }
        for r in db.get("reservations", [])
        if r.get("locator")
    ]


def apply_action(action: str, payload: dict | None = None) -> dict:
    payload = payload or {}
    db = _load()
    locator = str(payload.get("locator", "")).strip()

    if action == "add_reservation":
        if not locator:
            return view_data()
        rec = _find(db, locator)
        if rec is None:
            rec = {"locator": locator, "status": STATUS_PENDING, "reason": "", "created_at": _now()}
            db.setdefault("reservations", []).append(rec)
        provider = str(payload.get("provider", "")).strip()
        note = str(payload.get("note", "")).strip()
        date = str(payload.get("date", "")).strip()
        if provider:
            rec["provider"] = provider
        if note:
            rec["note"] = note
        if date:
            rec["date"] = date
        rec["updated_at"] = _now()
        store.save(WIDGET_ID, db)
        return view_data()

    if action == "mark_cancelled":
        rec = _find(db, locator)
        if rec:
            rec["status"] = STATUS_CANCELLED
            rec["reason"] = ""
            shot = str(payload.get("screenshot", "")).strip()
            if shot:
                rec["screenshot"] = shot
                rec["screenshot_opened"] = False
            rec["updated_at"] = _now()
            store.save(WIDGET_ID, db)
        return view_data()

    if action == "mark_failed":
        rec = _find(db, locator)
        if rec:
            rec["status"] = STATUS_ERROR
            rec["reason"] = str(payload.get("reason", "")).strip()[:200]
            shot = str(payload.get("screenshot", "")).strip()
            if shot:
                rec["screenshot"] = shot
                rec["screenshot_opened"] = False
            rec["updated_at"] = _now()
            store.save(WIDGET_ID, db)
        return view_data()

    if action == "view_screenshot":
        rec = _find(db, locator)
        shot = (rec or {}).get("screenshot", "")
        if rec and shot:
            path = os.path.join(store.data_dir(WIDGET_ID), shot)
            if os.path.isfile(path) and _open_in_system_viewer(path):
                rec["screenshot_opened"] = True
                rec["updated_at"] = _now()
                store.save(WIDGET_ID, db)
        return view_data()

    if action == "remove":
        before = len(db.get("reservations", []))
        db["reservations"] = [r for r in db.get("reservations", []) if r.get("locator") != locator]
        if len(db["reservations"]) != before:
            store.save(WIDGET_ID, db)
        return view_data()

    return view_data()
