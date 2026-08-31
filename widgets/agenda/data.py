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

# ── THE SAME COMMITMENT WRITTEN TWICE (V2-208) ────────────────────────────────────────────────────────────────
# Measured on `remember-and-remind-deadline` (2026-08-20 14:39), from the sandbox's own `state.json`:
#
#     meetings = [«renovar el seguro del coche» 2026-08-27, «Renovar el seguro del coche» 2026-08-27]
#
# Two rows for one obligation, differing by an article and a capital letter. V2-194 fixed this for the BACKSTOP
# (`router_guards.already_in_agenda`, which checks before dispatching) and the model's OWN data-op has no such
# guard: two turns, two `add_meeting`, nobody comparing. The guard belongs HERE, next to the write, so every
# writer present and future gets it — that is the same reasoning that put `already_in_agenda` next to its write
# rather than inside the pure decision.
#
# Why the TIME is part of the key and not just the day: two viewings of the same flat at 10:00 and 17:00 are two
# meetings, and a duplicate that is silently dropped is worse than a duplicate that is visible. So the rule is
# narrow ON PURPOSE — same day, same time, same title once articles/case/punctuation are gone. A legitimate
# repeat carries a different hour or a different title; what it never carries is the same three.
# …plus the widget's own category nouns (V2-473 round 5): «Cita dentista con los niños» and «Dentista con
# los niños» are the SAME commitment — the model re-titles on a retry and the dedup let both rows in, each
# spawning its default reminder. The category noun of the widget itself is title noise, not identity.
_ARTICLES = {"el", "la", "los", "las", "un", "una", "unos", "unas", "lo", "de", "del", "the", "a", "an",
             "cita", "reunion", "reunión", "meeting", "appointment", "evento"}


def _title_key(title: str) -> str:
    """Comparable form of a meeting title: no accents, no case, no punctuation, no articles."""
    words = re.findall(r"\w+", _strip_accents(str(title or "")).lower())
    return " ".join(w for w in words if w not in _ARTICLES)


def _is_same_meeting(a: dict, b: dict) -> bool:
    """Same day, same start time and the same title once the noise is gone.

    V2-473 round 6: at the SAME instant, one title's meaningful tokens being a SUBSET of the other's is
    also the same commitment («Llevar a los niños al dentista» vs «Dentista niños» landed as two meetings
    with two reminders). Disjoint titles at the same hour stay two meetings — a double-booked hour is the
    user's business, not ours to merge."""
    if str(a.get("date") or "") != str(b.get("date") or ""):
        return False
    if str(a.get("startTime") or "") != str(b.get("startTime") or ""):
        return False
    ka, kb = _title_key(a.get("title")), _title_key(b.get("title"))
    if not ka or not kb:
        return False
    if ka == kb:
        return True
    sa, sb = set(ka.split()), set(kb.split())
    return sa <= sb or sb <= sa

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


def _schedule_reminder(title: str, date: str, start: str, at: str = "", before_minutes: int = 120) -> tuple:
    """Schedule the appointment's notice. Returns (job_id, display) — ("", reason) when nothing was scheduled.

    V2-473: by default it falls `before_minutes` before the appointment (the operator's «avisos por
    defecto, en plan, dos horas antes», INI-026 A2); `at` overrides with an absolute «YYYY-MM-DD HH:MM».
    The prompt is RESOLVED content — what to say when it fires — never the user's raw sentence (the
    remember-and-remind lesson: a raw prompt re-asks the agent to schedule instead of reminding). A notice
    whose instant already passed is not scheduled: an alarm for the past is a fabrication with a bell.
    """
    import time as _t
    try:
        target = _t.mktime((int(date[:4]), int(date[5:7]), int(date[8:10]),
                            int(start[:2]), int(start[3:5]), 0, 0, 1, -1))
    except Exception:  # noqa: BLE001 — unreadable date/time → no notice, the write itself still lands
        return "", "fecha/hora ilegibles"
    if at:
        try:
            when = _t.mktime((int(at[:4]), int(at[5:7]), int(at[8:10]),
                              int(at[11:13]), int(at[14:16]), 0, 0, 1, -1))
        except Exception:  # noqa: BLE001
            return "", "instante del aviso ilegible"
    else:
        when = target - before_minutes * 60
        if when <= _t.time() + 60 < target:
            when = _t.time() + 60                      # appointment within the window → notice now-ish
    if when <= _t.time() or target <= _t.time() - 60:
        return "", "el instante ya pasó"
    stamp = _t.strftime("%Y-%m-%d %H:%M", _t.localtime(when))
    try:
        from voice.engine.core import langs as _langs
        _en = (_langs.current_code() or "es").lower() == "en"
    except Exception:  # noqa: BLE001
        _en = False
    prompt = (f"Remind the operator: «{title}» on {date} at {start}."
              if _en else f"Recuérdale al operador: «{title}» el {date} a las {start}.")
    try:
        from nucleo import scheduler as _sched
        r = _sched.create(prompt, stamp, name=f"aviso: {title[:80]}")
    except Exception as e:  # noqa: BLE001 — the scheduler must never lose the agenda WRITE
        return "", str(e)
    if not (r or {}).get("ok"):
        return "", str((r or {}).get("error") or "scheduler")
    return str(r.get("id") or ""), stamp


def _cancel_reminder(meeting: dict) -> None:
    """Cancel the meeting's scheduled notice, if it has one. Best-effort: an orphan alarm fires a ghost."""
    ref = str((meeting or {}).get("reminder_id") or "").strip()
    if not ref:
        return
    try:
        from nucleo import scheduler as _sched
        _sched.cancel(ref)
    except Exception:  # noqa: BLE001
        pass


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
        # V2-473 — the write does not INVENT. Measured in `dentist-appointment-into-agenda` round 1
        # (2026-08-29): an empty payload wrote «Cita, today, 17:00» — every field a default wearing the
        # face of success — and the reply said «Hecho.». A write with none of the real fields is an error
        # that names the expected keys (so the model retries with the right shape), never a silent row.
        if not any(str(payload.get(k) or "").strip() for k in ("title", "date", "startTime", "time")):
            return {"ok": False,
                    "error": "no me ha llegado ningún dato de la cita — vuelve a llamar a add_meeting "
                             "con el título, el día (YYYY-MM-DD) y la hora (HH:MM), sin preguntarle nada "
                             "al operador si ya te los dijo"}
        title = payload.get("title", "Cita")
        # V2-026: normalize spoken date/time into date=+1d and startTime='17:00' when appropriate, so the meeting
        # lands correctly even if the model does not calculate the date itself.
        _rawdate = str(payload.get("date", "") or "")
        # V2-473 round 3: three probe samples in a row sent `time`, not the manifest's `startTime`, and the
        # hour fell to the default AGAIN. The unambiguous natural alias must not cost the fact (V2-341).
        _rawtime = str(payload.get("startTime", "") or payload.get("time", "") or "")
        # V2-473 — the model's natural datetime shape («2026-09-08 15:00», or with a T) is BOTH fields in
        # one: the date resolver kept the date and silently dropped the hour, so «a las tres de la tarde»
        # became the 17:00 default. The glued hour fills startTime only when none was given explicitly.
        _m = re.match(r"^\s*(\d{4}-\d{2}-\d{2})[T ]+(\d{1,2}:\d{2})\s*$", _rawdate)
        if _m:
            _rawdate = _m.group(1)
            if not _rawtime.strip():
                _rawtime = _m.group(2)
        start = _resolve_time(_rawtime, default="17:00")
        date = _resolve_date(_rawdate)
        end = payload.get("endTime", "")
        if not re.match(r"^\d{1,2}[:h]\d{2}$|^\d{2}:\d{2}$", str(end)):
            eh = (int(start[:2]) + 1) % 24                 # no explicit end -> +1h
            end = f"{eh:02d}:{start[3:5]}"
        _new = {"title": title, "date": date, "startTime": start, "endTime": end}
        # V2-208: the SAME meeting twice (see `_is_same_meeting`). A duplicate notice is heard once; a duplicate
        # meeting is SEEN, and remains there until someone deletes it manually.
        if not any(_is_same_meeting(_new, m) for m in db.get("meetings", [])):
            # V2-473 — the default reminder is the AGENDA's job, not the model's conduct. Measured in
            # `dentist-appointment-into-agenda` round 2: asked for a notice, the model escalated to a WORKER
            # that died on Google's login screen, said «Hecho», and `scheduled_jobs` stayed empty. Telling
            # the agent an appointment schedules its notice (~2h before) with nobody asking (INI-026 A2);
            # moving it is `set_reminder`. Best-effort: a scheduler failure must not lose the WRITE — but
            # it is stored on the meeting, so the state never claims a notice that does not exist.
            _jid, _at = _schedule_reminder(title, date, start)
            if _jid:
                _new["reminder_id"], _new["remindAt"] = _jid, _at
            db.setdefault("meetings", []).append(_new)
    elif action == "cancel_meeting":
        # Cancel meeting(s) matching title (case-insensitive, accent-insensitive) plus optional date.
        title = _strip_accents((payload.get("title") or "").strip().lower())
        raw_date = payload.get("date", "")
        date = _resolve_date(raw_date) if raw_date else ""
        _keep, _gone = [], []
        for m in db.get("meetings", []):
            _hit = ((not title or title in _strip_accents(m.get("title", "").strip().lower()))
                    and (not date or m.get("date") == date))
            (_gone if _hit else _keep).append(m)
        db["meetings"] = _keep
        # V2-473 — an orphan alarm fires a ghost appointment: the reminder goes with its meeting.
        for m in _gone:
            _cancel_reminder(m)
    elif action == "set_reminder":
        # V2-473 — moving the notice is VOCABULARY (the clear_all lesson: a frequent intention with no
        # action cannot be gotten right). Finds the meeting like cancel_meeting does, cancels its current
        # reminder and schedules the new instant; errors NAME what is missing so the model can retry.
        title = _strip_accents((payload.get("title") or "").strip().lower())
        raw_date = payload.get("date", "")
        date = _resolve_date(raw_date) if raw_date else ""
        _hits = [m for m in db.get("meetings", [])
                 if (not title or title in _strip_accents(m.get("title", "").strip().lower()))
                 and (not date or m.get("date") == date)]
        if not title or not _hits:
            return {"ok": False,
                    "error": "no encuentro esa cita en la agenda — dime el título tal como está "
                             "apuntada (y la fecha si hay varias)"}
        _at = str(payload.get("at") or payload.get("time") or payload.get("startTime") or "").strip()
        _mm = re.match(r"^\s*(?:(\d{4}-\d{2}-\d{2})[T ]+)?(\d{1,2}:\d{2})\s*$", _at)
        if not _mm:
            return {"ok": False,
                    "error": "me falta la hora del aviso — mándala en `at` (HH:MM del día de la cita, "
                             "o YYYY-MM-DD HH:MM)"}
        m = _hits[0]
        _cancel_reminder(m)
        _when_date = _mm.group(1) or m.get("date") or _today()
        _hhmm = f"{int(_mm.group(2)[:_mm.group(2).index(':')]):02d}:{_mm.group(2)[-2:]}"
        _jid, _disp = _schedule_reminder(m.get("title", "Cita"), m.get("date", _when_date),
                                         m.get("startTime", ""), at=f"{_when_date} {_hhmm}")
        if not _jid:
            return {"ok": False, "error": f"no pude programar el aviso: {_disp}"}
        m["reminder_id"], m["remindAt"] = _jid, _disp
    elif action == "clear_all":
        # EMPTY THE ENTIRE AGENDA in ONE action (2026-08-14, session b70a45d0).
        #
        # The operator asked «vacía la agenda por completo, hoy y siempre» SIX times in four minutes and it was not
        # emptied. It was not a model failure: this API simply **could not express that intention**. There were only
        # single-item actions (`drop` one task, `cancel_meeting` one meeting, `drop_project` one project), so the
        # FlashBrain could only remove one thing per turn — and each turn said «hecho», which was true of the action
        # it had triggered and false of what it had been asked to do. On the 4th attempt it escalated to a worker,
        # which died holding the authorization because of another, separate failure.
        #
        # When a frequent intention does not fit in the declared vocabulary, the model has no way to get it right:
        # the answer is to expand the vocabulary, not fine-tune the prompt. The two slowest turns of the session
        # (25.6 s of TTFT each) were precisely the ones spent on this impossible decision.
        #
        # IRREVERSIBLE → the manifest marks it `confirm:true`, and the gate in `widgets/confirm.py` asks for yes/no first.
        # All THREE lists are emptied: without them, «por completo» would still be false. Projects are FROZEN
        # (`frozen`, the same state as `drop_project`) instead of being deleted: they are the operator's working
        # memory, and they asked for an empty agenda, not to lose what each project was about.
        for t in db.get("tasks", []):
            if t.get("status") in (None, "todo", "in_progress"):
                t["status"] = "dropped"
                t["updatedAt"] = _today()
        for p in db.get("projects", []):
            p["status"] = "frozen"
        for m in db.get("meetings", []):
            _cancel_reminder(m)                        # V2-473: emptied appointments take their alarms along
        db["meetings"] = []
        db["blocks"] = []
        # The day's FRAME (working hours, lunch time) is NOT touched: it comes from its configuration
        # (`lunchStart`/`lunchEnd`), not from anything the operator scheduled. Deleting it when asking for an empty
        # agenda would leave the schedule broken tomorrow without explaining why. Changing the frame is «cambia mi horario».

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
