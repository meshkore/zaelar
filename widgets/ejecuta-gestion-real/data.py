#
# Registro de Agentes — backend. Persiste el alta/estado/baja de agentes REALES del sistema en su propio
# store (widgets/_data/ejecuta-gestion-real/state.json), no solo en el DOM del widget.
#
import time
import uuid

from .. import store

DB_VERSION = 1
_STATUSES = ("activo", "inactivo", "error")


def _seed() -> dict:
    return {"agents": []}


def _migrate(db: dict, from_v: int) -> dict:
    return db


def _load() -> dict:
    return store.load("ejecuta-gestion-real", _seed(), version=DB_VERSION, migrate=_migrate)


def _fmt(ts: float) -> str:
    try:
        return time.strftime("%d/%m %H:%M", time.localtime(ts))
    except Exception:
        return "—"


def view_data(q: str = "") -> dict:
    db = _load()
    agents = sorted(db.get("agents", []), key=lambda a: a.get("registered_at", 0), reverse=True)
    return {
        "agents": [
            {
                "id": a.get("id", ""),
                "name": a.get("name", ""),
                "role": a.get("role", ""),
                "status": a.get("status", "activo"),
                "registered_at": _fmt(a.get("registered_at", 0)),
                "updated_at": _fmt(a.get("updated_at", a.get("registered_at", 0))),
            }
            for a in agents
        ],
        "count": len(agents),
    }


def ref_index() -> list:
    db = _load()
    return [
        {"id": a.get("id", ""), "label": a.get("name", a.get("id", "")), "field": "agentId", "hint": a.get("role", "")}
        for a in db.get("agents", [])
    ]


def apply_action(action: str, payload: dict | None = None) -> dict:
    payload = payload or {}
    db = _load()
    agents = db.setdefault("agents", [])

    if action == "register_agent":
        name = str(payload.get("name") or "").strip()
        if not name:
            return view_data()
        now = time.time()
        agents.append({
            "id": "a_" + uuid.uuid4().hex[:8],
            "name": name,
            "role": str(payload.get("role") or "").strip(),
            "status": "activo",
            "registered_at": now,
            "updated_at": now,
        })
        store.save("ejecuta-gestion-real", db)
        return view_data()

    if action == "update_status":
        agent_id = payload.get("agentId")
        status = str(payload.get("status") or "").strip().lower()
        if status not in _STATUSES:
            status = None
        for a in agents:
            if a.get("id") == agent_id:
                a["status"] = status or a.get("status", "activo")
                a["updated_at"] = time.time()
                store.save("ejecuta-gestion-real", db)
                break
        return view_data()

    if action == "remove_agent":
        agent_id = payload.get("agentId")
        before = len(agents)
        db["agents"] = [a for a in agents if a.get("id") != agent_id]
        if len(db["agents"]) != before:
            store.save("ejecuta-gestion-real", db)
        return view_data()

    return view_data()
