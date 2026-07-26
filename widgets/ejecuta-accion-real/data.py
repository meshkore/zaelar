#
# Ejecuta acción real — data layer. Refleja el patrón V2-061: cuando el FlashBrain (rápido) no puede completar
# una acción del mundo real (cancelar algo, comprar, enviar) la escala a un worker, que la EJECUTA de verdad y
# reporta aquí su progreso — pendiente → en curso → verificada/fallida — para que el operador vea que se
# COMPLETÓ EN LA REALIDAD, no que solo se anotó. Store aislado (widgets/_data/ejecuta-accion-real/state.json).
#
import time

from .. import store

WIDGET_ID = "ejecuta-accion-real"


def _empty() -> dict:
    return {"actions": [], "_seq": 0}


def load_db() -> dict:
    db = store.load(WIDGET_ID, _empty())
    db.setdefault("actions", [])
    db.setdefault("_seq", 0)
    return db


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M")


def _find(db: dict, action_id: str):
    for a in db.get("actions", []):
        if a.get("id") == action_id:
            return a
    return None


def view_data(q: str = "") -> dict:
    db = load_db()
    actions = sorted(db.get("actions", []), key=lambda a: a.get("createdAt", ""), reverse=True)
    return {
        "actions": actions,
        "count": len(actions),
        "pending": sum(1 for a in actions if a.get("status") in ("pending", "running")),
    }


def ref_index() -> list[dict]:
    """Acciones VIVAS (no verificadas) referenciables por voz — "esa acción de cancelar la ITV" resuelve al id
    real (V2-026); el modelo nunca lo inventa."""
    db = load_db()
    out = []
    for a in db.get("actions", []):
        if a.get("status") == "verified":
            continue
        out.append({"id": a["id"], "label": a.get("desc") or a["id"], "field": "actionId",
                    "hint": a.get("status", "")})
    return out


def apply_action(action: str, payload: dict | None = None) -> dict:
    """Data-ops (V2-025): el worker headless (puente hbwidget, V2-061) y el FlashBrain conducen esta tarjeta con
    estas acciones — encolar la acción real, reportar avance, y cerrarla verificada o fallida. Ninguna es
    irreversible por sí misma: solo REFLEJAN lo que ya ocurrió de verdad en el mundo/widget/memoria."""
    payload = payload or {}
    db = load_db()

    if action == "queue":
        db["_seq"] = int(db.get("_seq", 0)) + 1
        aid = f"act_{db['_seq']}"
        db.setdefault("actions", []).append({
            "id": aid,
            "desc": (payload.get("desc") or "").strip() or "Acción sin describir",
            "target": (payload.get("target") or "").strip(),
            "status": "pending",
            "steps": [],
            "reason": "",
            "createdAt": _now(),
            "updatedAt": _now(),
        })
        store.save(WIDGET_ID, db)
        return view_data()

    a = _find(db, payload.get("actionId"))
    if a is None:
        return view_data()

    if action == "progress":
        note = (payload.get("note") or "").strip()
        if note:
            a.setdefault("steps", []).append({"ts": _now(), "note": note})
        a["status"] = "running"
        a["updatedAt"] = _now()
    elif action == "verified":
        note = (payload.get("note") or "").strip()
        if note:
            a.setdefault("steps", []).append({"ts": _now(), "note": note})
        a["status"] = "verified"
        a["updatedAt"] = _now()
    elif action == "failed":
        a["status"] = "failed"
        a["reason"] = (payload.get("reason") or "").strip()
        a["updatedAt"] = _now()
    elif action == "retry":
        a["status"] = "pending"
        a["reason"] = ""
        a["updatedAt"] = _now()
    elif action == "dismiss":
        db["actions"] = [x for x in db.get("actions", []) if x.get("id") != a.get("id")]

    store.save(WIDGET_ID, db)
    return view_data()
