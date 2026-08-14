#
# Agenda widget — data layer (HANDOFF §9). loadData (seed on first run) · computePlan · applyAction.
# Reads/writes ONLY the widget's isolated store ("widgets/_data/agenda.json") — no coupling to the voice core.
#
import json
import os
import re
import time
import unicodedata

from .. import store
from . import planner


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c))

HERE = os.path.dirname(os.path.abspath(__file__))
WIDGET_ID = "agenda"


def _seed() -> dict:
    return json.load(open(os.path.join(HERE, "seed.json"), encoding="utf-8"))


# Store schema version (lazy migration on read — see store.load). Bump when the shape of agenda.json changes
# and handle the upgrade in _migrate(); old files upgrade the first time the new code reads them.
DB_VERSION = 1


def _migrate(db: dict, from_v: int) -> dict:
    # v0 → v1: pre-versioning files are already the current shape; just adopt the version field.
    return db


def load_db() -> dict:
    if not store.exists(WIDGET_ID):
        store.save(WIDGET_ID, _seed())
    return store.load(WIDGET_ID, _seed(), version=DB_VERSION, migrate=_migrate)


def _today() -> str:
    return time.strftime("%Y-%m-%d")


def _now() -> str:
    return time.strftime("%H:%M")


def compute_plan(db: dict | None = None) -> dict:
    # PURE: derive the day plan; do NOT persist on read (avoids read-modify-write races; GET stays idempotent).
    return planner.plan_day(db or load_db(), date=_today(), now=_now())


_WEEK_LABELS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]


def _horizon(db: dict, span: int = 7) -> list[dict]:
    """Per-day plans for TODAY .. TODAY+span-1, so the widget exposes a time horizon (not only today) and
    switches views client-side without another request (widget.js cannot fetch). `plan_day` is pure and cheap."""
    import time as _t
    today = _today()
    base = _t.mktime(_t.localtime())
    out: list[dict] = []
    for i in range(span):
        d = _t.localtime(base + i * 86400)
        date = _t.strftime("%Y-%m-%d", d)
        plan = planner.plan_day(db, date=date, now=_now() if date == today else "")
        label = "Hoy" if i == 0 else ("Mañana" if i == 1 else _WEEK_LABELS[d.tm_wday])
        out.append({"date": date, "label": label, "weekday": _WEEK_LABELS[d.tm_wday], "plan": plan})
    return out


def view_data(q: str = "") -> dict:
    """Everything the render needs: the day horizon (today + upcoming days for tabs), today's plan, the active
    live block, projects, warnings/coaching."""
    db = load_db()
    days = _horizon(db)
    plan = days[0]["plan"]
    return {
        "date": plan["date"], "now": _now(),
        "mission": db.get("mission", ""),
        "plan": plan,
        "active": planner.active_block(plan, _now()),
        "days": days, "todayIndex": 0,
        "meetings": db.get("meetings", []),           # dated meetings -> full MONTH view (client-side calendar)
        "projects": db.get("projects", []),
        "warnings": plan.get("warnings", []),
        "coaching": plan.get("coaching", []),
    }


def ref_index() -> list[dict]:
    """Items the brain can reference by voice (V2-026): live tasks (by title) and active projects (by name).
    `field` is the payload key that identifies them in actions (`taskId` for a task, `projectId` for a project),
    so `widgets/refs.py` resolves a spoken task reference to its id without the model guessing it.
    Only current items are exposed; completed/dropped tasks are no longer referenceable."""
    db = load_db()
    out: list[dict] = []
    for t in db.get("tasks", []):
        if t.get("status") in ("done", "dropped"):
            continue
        out.append({"id": t["id"], "label": t.get("title") or t["id"], "field": "taskId",
                    "hint": (t.get("startTime") or "") + ("" if t.get("status") in (None, "todo") else f" {t['status']}")})
    for p in db.get("projects", []):
        if p.get("status") == "frozen":
            continue
        out.append({"id": p["id"], "label": p.get("name") or p["id"], "field": "projectId", "hint": "proyecto"})
    return out


# Relative spoken date/time normalization (V2-026).
_WEEKDAYS = {"lunes": 0, "martes": 1, "miercoles": 2, "miércoles": 2, "jueves": 3, "viernes": 4,
             "sabado": 5, "sábado": 5, "domingo": 6}


def _resolve_date(raw: str) -> str:
    """Convert a spoken relative date (tomorrow, today, the day after tomorrow, a weekday, or already 'YYYY-MM-DD') into
    'YYYY-MM-DD'. Sensible default: today. This keeps a relative-date appointment correctly placed even when the
    model does not calculate the date itself."""
    import time as _t
    s = (raw or "").strip().lower()
    if not s:
        return _today()
    if len(s) >= 8 and s[:4].isdigit() and "-" in s:      # already comes as YYYY-MM-DD
        return s[:10]
    n = _strip_accents(s)
    today = _t.localtime()
    base = _t.mktime(today)
    day = 86400
    if "pasado manana" in n:
        return _t.strftime("%Y-%m-%d", _t.localtime(base + 2 * day))
    if "manana" in n:
        return _t.strftime("%Y-%m-%d", _t.localtime(base + day))
    if "hoy" in n:
        return _today()
    for name, wd in _WEEKDAYS.items():
        nn = _strip_accents(name)
        if nn in n:
            delta = (wd - today.tm_wday) % 7
            delta = delta or 7                             # weekday references mean the next matching day, not today
            return _t.strftime("%Y-%m-%d", _t.localtime(base + delta * day))
    return _today()


def _resolve_time(raw: str, default: str = "17:00") -> str:
    """Normalize a spoken time (natural language hour, meridiem, '17h', or '17:00') into 'HH:MM'. Defaults 1-7 without an
    explicit meridiem to afternoon, because appointments are more often requested for evening than early morning."""
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
        elif not am and 1 <= h <= 7:                       # bare 1-7 without am/pm -> afternoon
            h += 12
        return f"{h % 24:02d}:00"
    return default


def apply_action(action: str, payload: dict | None = None) -> dict:
    """Widget actions (HANDOFF §9.3): mark done / not now / snooze / drop / replan. Mutates the isolated store."""
    payload = payload or {}
    db = load_db()
    tid = payload.get("taskId")
    tasks = {t["id"]: t for t in db.get("tasks", [])}

    if action == "done" and tid in tasks:
        tasks[tid]["status"] = "done"; tasks[tid]["updatedAt"] = _today()
    elif action == "not_now" and tid in tasks:                     # "ahora no me apetece" -> avoidance++ (coaching)
        tasks[tid]["avoidance"] = int(tasks[tid].get("avoidance", 0)) + 1
    elif action == "snooze" and tid in tasks:
        tasks[tid]["snoozedUntil"] = _today()
    elif action == "drop" and tid in tasks:
        tasks[tid]["status"] = "dropped"
    elif action == "drop_project":
        pid = payload.get("projectId")
        for p in db.get("projects", []):
            if p["id"] == pid:
                p["status"] = "frozen"
        for t in db.get("tasks", []):
            if t.get("projectId") == pid and t.get("status") in (None, "todo", "in_progress"):
                t["status"] = "dropped"
    elif action == "add_meeting":
        title = payload.get("title", "Cita")
        # V2-026: normalize spoken date/time into date=+1d and startTime='17:00' when appropriate, so the meeting
        # lands correctly even if the model does not calculate the date itself.
        start = _resolve_time(payload.get("startTime", ""), default="17:00")
        date = _resolve_date(payload.get("date", ""))
        end = payload.get("endTime", "")
        if not re.match(r"^\d{1,2}[:h]\d{2}$|^\d{2}:\d{2}$", str(end)):
            eh = (int(start[:2]) + 1) % 24                 # no explicit end -> +1h
            end = f"{eh:02d}:{start[3:5]}"
        db.setdefault("meetings", []).append({
            "title": title,
            "date": date,
            "startTime": start,
            "endTime": end,
        })
    elif action == "cancel_meeting":
        # Cancel meeting(s) matching title (case-insensitive, accent-insensitive) plus optional date.
        title = _strip_accents((payload.get("title") or "").strip().lower())
        raw_date = payload.get("date", "")
        date = _resolve_date(raw_date) if raw_date else ""
        db["meetings"] = [
            m for m in db.get("meetings", [])
            if not (
                (not title or title in _strip_accents(m.get("title", "").strip().lower()))
                and (not date or m.get("date") == date)
            )
        ]
    elif action == "clear_all":
        # VACIAR LA AGENDA ENTERA, en UNA acción (2026-08-14, sesión b70a45d0).
        #
        # El operador pidió «vacía la agenda por completo, hoy y siempre» SEIS veces en cuatro minutos y no se
        # vació. No era un fallo del modelo: es que esta API **no sabía expresar esa intención**. Solo había
        # acciones de UN elemento (`drop` una tarea, `cancel_meeting` una cita, `drop_project` un proyecto), así
        # que el FlashBrain solo podía tirar una cosa por turno — y cada turno decía «hecho», que era verdad de la
        # acción que había disparado y mentira de lo que le habían pedido. Al 4º intento acabó escalando a un
        # worker, que murió con la autorización en la mano por otro fallo distinto.
        #
        # Cuando una intención frecuente no cabe en el vocabulario declarado, el modelo no tiene forma de acertar:
        # la respuesta es ampliar el vocabulario, no afinar el prompt. Los dos turnos más lentos de la sesión
        # (25,6 s de TTFT cada uno) fueron precisamente los de esta decisión imposible.
        #
        # IRREVERSIBLE → el manifest la marca `confirm:true` y el gate de `widgets/confirm.py` pide un sí/no antes.
        # Se vacían las TRES listas: sin ellas «por completo» seguiría siendo mentira. Los proyectos se CONGELAN
        # (`frozen`, el mismo estado que `drop_project`) en vez de borrarse: son la memoria de trabajo del
        # operador, y él pidió una agenda vacía, no perder de qué iba cada proyecto.
        for t in db.get("tasks", []):
            if t.get("status") in (None, "todo", "in_progress"):
                t["status"] = "dropped"
                t["updatedAt"] = _today()
        for p in db.get("projects", []):
            p["status"] = "frozen"
        db["meetings"] = []
        db["blocks"] = []
        # NO se toca el MARCO del día (horario laboral, hora de comer): eso sale de su configuración
        # (`lunchStart`/`lunchEnd`), no de nada que él haya agendado. Borrárselo por pedir una agenda vacía le
        # dejaría el horario roto mañana sin saber por qué. Cambiar el marco es «cambia mi horario».

    # 'replan' (and any action) just recomputes below
    db["currentPlan"] = compute_plan(db)  # persist the updated plan too, not just the mutation
    store.save(WIDGET_ID, db)   # persist the mutation; the plan is derived fresh in view_data()
    return view_data()


def coach_context() -> str:
    """The 'memory seam' (HANDOFF §7 note): mission + workday + projects-by-priority + today's plan + free gaps,
    rendered for the assistant to adopt the COACH role over the agenda."""
    d = view_data()
    db = load_db()
    lines = [f"MISIÓN GLOBAL: {d['mission']}", "", "PROYECTOS (por prioridad):"]
    for p in sorted(db.get("projects", []), key=lambda p: p.get("priority", 5)):
        lines.append(f"- [{p.get('priority')}] {p['name']}: {p.get('objective','')} "
                     f"(valor {p.get('expectedValue')}, prob {p.get('successProbability')}, {p.get('hoursRemaining')}h)")
    lines.append("\nAGENDA DE HOY:")
    for b in d["plan"]["blocks"]:
        lines.append(f"  {b['start']}–{b['end']} · {b['label']} ({b['kind']})")
    if d["active"]:
        lines.append(f"\nAHORA ({d['now']}): {d['active']['label']} · quedan {d['active'].get('remaining_min','?')} min")
    if d["warnings"]:
        lines.append("\nNO CABE HOY: " + " | ".join(d["warnings"]))
    return "\n".join(lines)
