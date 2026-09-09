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

# V2-639 — the plan's own words follow the active language. The planner stays PURE (lang is an argument,
# the caller reads the engine's current code); only the strings the planner INVENTS are here — titles the
# operator dictated pass through untouched, they are data.
_L = {
    "es": {"block": "Bloque", "meeting": "Reunión", "task": "Tarea", "lunch": "Comida",
           "exercise": "Ejercicio", "break": "Descanso", "summary": "{n} tareas planificadas",
           "overflow": "No cabe hoy: «{t}» ({d}m) — coste de oportunidad.",
           "avoid": "Llevas evitando «{t}» — ¿de verdad te interesa, o lo quitamos del scope?",
           "advance": "avanza {p} (prioridad {pr})", "priority": "prioridad"},
    "en": {"block": "Block", "meeting": "Meeting", "task": "Task", "lunch": "Lunch",
           "exercise": "Exercise", "break": "Break", "summary": "{n} tasks planned",
           "overflow": "Does not fit today: “{t}” ({d}m) — opportunity cost.",
           "avoid": "You keep avoiding “{t}” — do you actually want it, or shall we drop it?",
           "advance": "advances {p} (priority {pr})", "priority": "priority"},
}


def _lbl(lang: str) -> dict:
    return _L.get((lang or "es").lower()[:2], _L["es"])


def plan_day(db: dict, date: str = "", now: str = "", lang: str = "") -> dict:
    L = _lbl(lang)
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
            reserved.append((_m(r["startTime"]), _m(r["endTime"]), r.get("title", L["block"]), "personal", {}))
    for mt in db.get("meetings", []):
        if not date or str(mt.get("date", "")).startswith(date):
            reserved.append((_m(mt["startTime"]), _m(mt["endTime"]), mt.get("title", L["meeting"]), "meeting", {}))
    for t in db.get("tasks", []):
        if t.get("fixed") and t.get("startTime") and t.get("status") in (None, "todo", "in_progress"):
            s = _m(t["startTime"]); reserved.append((s, s + int(t.get("estimateMinutes", 30)),
                                                      t.get("title", L["task"]), "deep" if t.get("deep") else "admin",
                                                      {"taskId": t["id"], "projectId": t.get("projectId")}))

    # 2) reserve lunch + exercise
    if user.get("lunchStart") and user.get("lunchEnd"):
        reserved.append((_m(user["lunchStart"]), _m(user["lunchEnd"]), L["lunch"], "break", {}))
    if user.get("wantsExercise"):
        reserved.append((max(ws, we - 45), we, L["exercise"], "exercise", {}))

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
                blocks.append({"start": _hhmm(gs), "end": _hhmm(gs + dur), "label": t.get("title", L["task"]),
                               "kind": "deep" if t.get("deep") else "admin",
                               "taskId": t["id"], "projectId": t.get("projectId"),
                               "why": _why(t, projects, L)})
                gs += dur; used_focus += dur
                if used_focus >= 90 and ge - gs >= 15:
                    blocks.append({"start": _hhmm(gs), "end": _hhmm(gs + 15), "label": L["break"], "kind": "break"})
                    gs += 15; used_focus = 0
                gaps[gi][0] = gs
                placed = True
                break
            gi += 1
        if not placed:
            warnings.append(L["overflow"].format(t=t.get("title", L["task"]), d=dur))

    blocks.sort(key=lambda b: _m(b["start"]))

    # 6) focus (objectives, by priority/ROI) + coaching nudges (avoidance ≥ 3)
    focus = []
    seen = set()
    for t in cand:
        pid = t.get("projectId")
        if pid and pid not in seen:
            seen.add(pid); p = projects.get(pid, {})
            focus.append({"projectId": pid, "label": p.get("name", pid), "objective": p.get("objective", ""),
                          "why": f"{L['priority']} {p.get('priority', '?')} · ROI {project_roi(p):.0f}"})
    coaching = [L["avoid"].format(t=t["title"])
                for t in db.get("tasks", []) if int(t.get("avoidance", 0)) >= 3]

    return {"date": date, "greeting": "", "focus": focus[:3], "blocks": blocks,
            "summary": L["summary"].format(n=len([b for b in blocks if b["kind"] in ("deep", "admin")])),
            "warnings": warnings, "coaching": coaching, "generatedBy": "heuristic"}


def _why(t: dict, projects: dict, L: dict | None = None) -> str:
    L = L or _lbl("")
    p = projects.get(t.get("projectId"), {})
    return L["advance"].format(p=p.get("name", ""), pr=p.get("priority", "?")) if p else ""


def active_block(plan: dict, now: str = "") -> dict | None:
    """The block whose clock window contains 'now' (HH:MM). Drives the live 'current task' + countdown."""
    cur = _m(now) if now else (datetime.now().hour * 60 + datetime.now().minute)
    for b in plan.get("blocks", []):
        if _m(b["start"]) <= cur < _m(b["end"]):
            return {**b, "remaining_min": _m(b["end"]) - cur}
    return None
