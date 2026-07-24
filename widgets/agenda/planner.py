#
# Deterministic day planner — PURE function (no IO, no LLM), ported from the POS (HANDOFF §6.3).
# Builds a DayPlan from the DB: fixes recurring/meetings, reserves lunch+exercise, finds free gaps, orders
# candidate tasks by priority → project ROI → energy, places them, inserts breaks, overflow → warnings.
#
from datetime import datetime


def _m(hhmm: str) -> int:
    h, m = str(hhmm or "0:0").split(":")[:2]
    return int(h) * 60 + int(m)


def _hhmm(mins: int) -> str:
    mins = max(0, int(mins))
    return f"{mins // 60:02d}:{mins % 60:02d}"


def _clamp01(x):
    try:
        return max(0.0, min(1.0, float(x)))
    except Exception:
        return 0.0


def project_roi(p: dict) -> float:
    return (float(p.get("expectedValue", 0)) * _clamp01(p.get("successProbability", 0))) / \
           (max(1.0, float(p.get("hoursRemaining", 1))) + float(p.get("monthlyCost", 0)) / 50.0)


ENERGY_RANK = {"low": 0, "medium": 1, "high": 2}


def plan_day(db: dict, date: str = "", now: str = "") -> dict:
    user = db.get("user", {})
    ws, we = _m(user.get("workStart", "09:00")), _m(user.get("workEnd", "18:00"))
    projects = {p["id"]: p for p in db.get("projects", [])}
    weekday = datetime.fromisoformat(date).weekday() if date else datetime.now().weekday()  # 0=Mon

    reserved = []   # (start,end,label,kind,meta)

    # 1) fixed: recurring for this weekday + meetings today + tasks with fixed startTime
    for r in db.get("recurring", []):
        if not r.get("active", True):
            continue
        days = r.get("days", "daily")
        ok = days == "daily" or (isinstance(days, list) and ((weekday + 1) % 7) in days)
        if ok:
            reserved.append((_m(r["startTime"]), _m(r["endTime"]), r.get("title", "Bloque"), "personal", {}))
    for mt in db.get("meetings", []):
        if not date or str(mt.get("date", "")).startswith(date):
            reserved.append((_m(mt["startTime"]), _m(mt["endTime"]), mt.get("title", "Reunión"), "meeting", {}))
    for t in db.get("tasks", []):
        if t.get("fixed") and t.get("startTime") and t.get("status") in (None, "todo", "in_progress"):
            s = _m(t["startTime"]); reserved.append((s, s + int(t.get("estimateMinutes", 30)),
                                                      t.get("title", "Tarea"), "deep" if t.get("deep") else "admin",
                                                      {"taskId": t["id"], "projectId": t.get("projectId")}))

    # 2) reserve lunch + exercise
    if user.get("lunchStart") and user.get("lunchEnd"):
        reserved.append((_m(user["lunchStart"]), _m(user["lunchEnd"]), "Comida", "break", {}))
    if user.get("wantsExercise"):
        reserved.append((max(ws, we - 45), we, "Ejercicio", "exercise", {}))

    reserved = sorted([r for r in reserved if r[1] > ws and r[0] < we], key=lambda r: r[0])

    # 3) free gaps = workday − reserved
    gaps, cursor = [], ws
    for s, e, *_ in reserved:
        if s > cursor:
            gaps.append([cursor, s])
        cursor = max(cursor, e)
    if cursor < we:
        gaps.append([cursor, we])

    # 4) candidate tasks ordered by priority → ROI → energy (deep last if low energy)
    low = user.get("energy") == "low"
    cand = [t for t in db.get("tasks", [])
            if t.get("status") in (None, "todo", "in_progress") and not t.get("fixed")
            and not t.get("snoozedUntil")]

    def keyfn(t):
        roi = project_roi(projects.get(t.get("projectId"), {}))
        deep_penalty = (1 if (low and t.get("deep")) else 0)
        return (deep_penalty, int(t.get("priority", 3)), -roi, ENERGY_RANK.get(t.get("energy", "medium"), 1))
    cand.sort(key=keyfn)

    # 5) place tasks in gaps; 15m break after ~90m focus
    blocks, warnings, used_focus = [], [], 0
    for s, e, label, kind, meta in reserved:
        blocks.append({"start": _hhmm(s), "end": _hhmm(e), "label": label, "kind": kind, **meta})
    gi = 0
    for t in cand:
        dur = int(t.get("estimateMinutes", 30))
        placed = False
        while gi < len(gaps):
            gs, ge = gaps[gi]
            if ge - gs >= dur:
                blocks.append({"start": _hhmm(gs), "end": _hhmm(gs + dur), "label": t.get("title", "Tarea"),
                               "kind": "deep" if t.get("deep") else "admin",
                               "taskId": t["id"], "projectId": t.get("projectId"),
                               "why": _why(t, projects)})
                gs += dur; used_focus += dur
                if used_focus >= 90 and ge - gs >= 15:
                    blocks.append({"start": _hhmm(gs), "end": _hhmm(gs + 15), "label": "Descanso", "kind": "break"})
                    gs += 15; used_focus = 0
                gaps[gi][0] = gs
                placed = True
                break
            gi += 1
        if not placed:
            warnings.append(f"No cabe hoy: «{t.get('title','tarea')}» ({dur}m) — coste de oportunidad.")

    blocks.sort(key=lambda b: _m(b["start"]))

    # 6) focus (objectives, by priority/ROI) + coaching nudges (avoidance ≥ 3)
    focus = []
    seen = set()
    for t in cand:
        pid = t.get("projectId")
        if pid and pid not in seen:
            seen.add(pid); p = projects.get(pid, {})
            focus.append({"projectId": pid, "label": p.get("name", pid), "objective": p.get("objective", ""),
                          "why": f"prioridad {p.get('priority','?')} · ROI {project_roi(p):.0f}"})
    coaching = [f"Llevas evitando «{t['title']}» — ¿de verdad te interesa, o lo quitamos del scope?"
                for t in db.get("tasks", []) if int(t.get("avoidance", 0)) >= 3]

    return {"date": date, "greeting": "", "focus": focus[:3], "blocks": blocks,
            "summary": f"{len([b for b in blocks if b['kind'] in ('deep','admin')])} tareas planificadas",
            "warnings": warnings, "coaching": coaching, "generatedBy": "heuristic"}


def _why(t: dict, projects: dict) -> str:
    p = projects.get(t.get("projectId"), {})
    return f"avanza {p.get('name','')} (prioridad {p.get('priority','?')})" if p else ""


def active_block(plan: dict, now: str = "") -> dict | None:
    """The block whose clock window contains 'now' (HH:MM). Drives the live 'current task' + countdown."""
    cur = _m(now) if now else (datetime.now().hour * 60 + datetime.now().minute)
    for b in plan.get("blocks", []):
        if _m(b["start"]) <= cur < _m(b["end"]):
            return {**b, "remaining_min": _m(b["end"]) - cur}
    return None
