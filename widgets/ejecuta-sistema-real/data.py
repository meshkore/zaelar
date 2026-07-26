#
# Ejecución en el sistema real — backend. La incorporación de un agente nuevo NO es un mockup del widget: cada
# paso hace un efecto REAL y persistente en disco (crear el registro, releerlo para verificar su integridad,
# activarlo), así el estado que se ve aquí es exactamente el que sobrevive a un reinicio — nunca una animación.
#
import json
import os
import re
import time
import unicodedata

from .. import store

WIDGET_ID = "ejecuta-sistema-real"
DB_VERSION = 1


def _seed() -> dict:
    return {"agents": []}


def _migrate(db: dict, from_v: int) -> dict:
    return db


def load_db() -> dict:
    return store.load(WIDGET_ID, _seed(), version=DB_VERSION, migrate=_migrate)


def _slug(name: str) -> str:
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode("ascii").lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return "a_" + (s or "agente")


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _execute_onboarding(agent_id: str, name: str, role: str) -> tuple[list[dict], bool]:
    """Los pasos REALES del alta — cada uno con un efecto persistente y verificable, no un temporizador de
    mentira. Si un paso falla, se corta ahí y el agente queda 'incompleto' (retry reintenta desde cero)."""
    steps: list[dict] = []

    ok_name = bool((name or "").strip())
    steps.append({"label": "validar nombre", "status": "ok" if ok_name else "fail",
                  "detail": "" if ok_name else "nombre vacío"})
    if not ok_name:
        return steps, False

    agent_dir = os.path.join(store.data_dir(WIDGET_ID), "agents", agent_id)
    cfg_path = os.path.join(agent_dir, "config.json")
    try:
        os.makedirs(agent_dir, exist_ok=True)
        cfg = {"id": agent_id, "name": name, "role": role or "", "created_at": _now()}
        tmp = cfg_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, cfg_path)
        steps.append({"label": "crear área de trabajo", "status": "ok", "detail": "registro escrito en disco"})
    except Exception as e:
        steps.append({"label": "crear área de trabajo", "status": "fail", "detail": str(e)[:120]})
        return steps, False

    try:
        with open(cfg_path, encoding="utf-8") as f:
            back = json.load(f)
        ok_read = back.get("id") == agent_id and back.get("name") == name
        steps.append({"label": "verificar integridad", "status": "ok" if ok_read else "fail",
                      "detail": "registro releído y comprobado" if ok_read else "el registro no coincide"})
        if not ok_read:
            return steps, False
    except Exception as e:
        steps.append({"label": "verificar integridad", "status": "fail", "detail": str(e)[:120]})
        return steps, False

    steps.append({"label": "activar en el sistema", "status": "ok", "detail": "agente activo"})
    return steps, True


def apply_action(action: str, payload: dict | None = None) -> dict:
    payload = payload or {}
    db = load_db()
    agents = db.setdefault("agents", [])

    if action == "onboard_agent":
        name = (payload.get("name") or "").strip()
        role = (payload.get("role") or "").strip()
        if name:
            agent_id = _slug(name)
            steps, ok = _execute_onboarding(agent_id, name, role)
            rec = {"id": agent_id, "name": name, "role": role,
                   "status": "activo" if ok else "incompleto", "steps": steps, "updated_at": _now()}
            db["agents"] = [a for a in agents if a.get("id") != agent_id] + [rec]
            store.save(WIDGET_ID, db)

    elif action == "retry":
        agent_id = (payload.get("agentId") or "").strip()
        agent = next((a for a in agents if a.get("id") == agent_id), None)
        if agent:
            steps, ok = _execute_onboarding(agent_id, agent.get("name", ""), agent.get("role", ""))
            agent["steps"] = steps
            agent["status"] = "activo" if ok else "incompleto"
            agent["updated_at"] = _now()
            store.save(WIDGET_ID, db)

    elif action == "remove_agent":
        agent_id = (payload.get("agentId") or "").strip()
        for a in agents:
            if a.get("id") == agent_id:
                a["status"] = "baja"
                a["updated_at"] = _now()
        store.save(WIDGET_ID, db)

    return view_data()


def tick(ctx=None) -> None:
    """BACKGROUND (V2-034, manifest `"background":"1m"`): ejecuta de verdad la acción PENDIENTE — reintenta,
    fuera del hot path, cualquier agente que quedó `incompleto` (el paso que falló) hasta que se complete en el
    sistema real, y actualiza su estado tras la ejecución. También cubre el alta que YA se completó al instante
    (apply_action no tiene acceso a memoria, es stdlib-only) — cualquier agente `activo` aún no volcado
    (`remembered` ausente) se refleja aquí, así ninguna gestión real ejecutada — ni la reintentada ni la
    inmediata — se queda sin memoria, aunque la tarjeta no se haya abierto."""
    try:
        db = load_db()
        agents = db.get("agents", [])
        changed = False
        for a in agents:
            if a.get("status") == "incompleto":
                steps, ok = _execute_onboarding(a["id"], a.get("name", ""), a.get("role", ""))
                a["steps"] = steps
                a["status"] = "activo" if ok else "incompleto"
                a["updated_at"] = _now()
                changed = True
            if a.get("status") == "activo" and not a.get("remembered") and ctx is not None:
                ctx.remember(f"Alta real completada: agente \"{a.get('name') or a['id']}\" activo en el sistema.",
                              slot=f"ejecuta-sistema-real:{a['id']}", kind="note", importance=0.3)
                a["remembered"] = True
                changed = True
        if changed:
            store.save(WIDGET_ID, db)
    except Exception:
        pass


def ref_index() -> list[dict]:
    db = load_db()
    return [{"id": a["id"], "label": a.get("name") or a["id"], "field": "agentId"}
            for a in db.get("agents", []) if a.get("status") != "baja"]


def view_data(q: str = "") -> dict:
    db = load_db()
    agents = db.get("agents", [])
    return {"agents": agents, "count": len(agents)}
