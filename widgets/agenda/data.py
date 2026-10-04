#
# Agenda widget — data layer (HANDOFF §9). loadData (seed on first run) · computePlan · applyAction.
# Reads/writes ONLY the widget's isolated store ("widgets/_data/agenda.json") — no coupling to the voice core.
#
import json
import os
import re
import time

from .. import store
from . import gcal, sweep
from .reminders import _cancel_reminder, _schedule_reminder  # noqa: F401  (V2-705)
from .details import _apply_details, _norm_attendees, _norm_status  # noqa: F401
from . import edit, planner, recur, tasklists


# `_strip_accents` travelled with the spoken-date resolver it serves (V2-744); re-exported under its
# historical name because `_title_key` below and half this widget's tests reach it here.
from .when import _strip_accents  # noqa: E402
from .twins import (  # noqa: E402,F401 — V2-778 F1: moved, imported back under their names
    _ARTICLES, _is_same_meeting, _settle_rule, _title_key, _titles_overlap)


HERE = os.path.dirname(os.path.abspath(__file__))
WIDGET_ID = "agenda"


def _seed() -> dict:
    return json.load(open(os.path.join(HERE, "seed.json"), encoding="utf-8"))


# Store schema version (lazy migration on read — see store.load). Bump when the shape of agenda.json changes
# and handle the upgrade in _migrate(); old files upgrade the first time the new code reads them.
DB_VERSION = 2


def _migrate(db: dict, from_v: int) -> dict:
    # v0 → v1: pre-versioning files are already the current shape; just adopt the version field.
    # v1 → v2 (V2-744): tasks live in NUMBERED LISTS. Every task without a `listId` joins «General», and
    # the list itself is created if it is not there — see `tasklists.migrate` for why it also runs on read.
    return tasklists.migrate(db)


def load_db() -> dict:
    if not store.exists(WIDGET_ID):
        store.save(WIDGET_ID, _seed())
    return store.load(WIDGET_ID, _seed(), version=DB_VERSION, migrate=_migrate)


def _today() -> str:
    return time.strftime("%Y-%m-%d")


def _shift(days: int) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(time.time() + days * 86400))


def _now() -> str:
    return time.strftime("%H:%M")


def _spoken(field: str) -> str:
    """A line the operator HEARS, read from the language table instead of written here (V2-689).

    His rule, and V2-676's receipt: every text the operator can hear or read lives in ONE place that gets
    translated when the agent is initialised in a language. A hardcoded Spanish refusal is a defect for
    every operator who is not speaking Spanish — and an `_en` ternary is the same defect for the third
    language, which is why this reads the TABLE and never a two-way branch.

    Fail-safe: an unreadable table falls back to the field's own default, which is the Castilian text that
    used to be inline. A refusal the operator cannot hear is worse than one in the wrong language."""
    try:
        from i18n import langs as _langs
        return str(getattr(_langs.spec(), field, "") or "")
    except Exception:  # noqa: BLE001
        from dataclasses import fields as _fields
        try:
            from i18n.langs import LangSpec as _LS
            return str(next(f.default for f in _fields(_LS) if f.name == field))
        except Exception:  # noqa: BLE001
            return ""


def _lang() -> str:
    """Active engine language code ('es'/'en'…), best-effort — V2-639: the plan speaks the operator's language."""
    try:
        from voice.engine.core import langs as _langs
        return (_langs.current_code() or "es").lower()
    except Exception:  # noqa: BLE001
        return "es"


def compute_plan(db: dict | None = None) -> dict:
    # PURE: derive the day plan; do NOT persist on read (avoids read-modify-write races; GET stays idempotent).
    return planner.plan_day(db or load_db(), date=_today(), now=_now(), lang=_lang())


_WEEK_LABELS = {"es": ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"],
                "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]}
_DAY_WORDS = {"es": ("Hoy", "Mañana"), "en": ("Today", "Tomorrow")}


def _horizon(db: dict, span: int = 7) -> list[dict]:
    """Per-day plans for TODAY .. TODAY+span-1, so the widget exposes a time horizon (not only today) and
    switches views client-side without another request (widget.js cannot fetch). `plan_day` is pure and cheap."""
    import time as _t
    today = _today()
    base = _t.mktime(_t.localtime())
    lang = _lang()
    wk = _WEEK_LABELS.get(lang[:2], _WEEK_LABELS["es"])
    words = _DAY_WORDS.get(lang[:2], _DAY_WORDS["es"])
    out: list[dict] = []
    for i in range(span):
        d = _t.localtime(base + i * 86400)
        date = _t.strftime("%Y-%m-%d", d)
        plan = planner.plan_day(db, date=date, now=_now() if date == today else "", lang=lang)
        label = words[0] if i == 0 else (words[1] if i == 1 else wk[d.tm_wday])
        out.append({"date": date, "label": label, "weekday": wk[d.tm_wday], "plan": plan})
    return out


# How long a pushed view stays worth OBEYING (V2-540). It is not the mounted widget that needs this — that one
# keeps whatever is on screen and only moves when the token changes — it is a widget mounting FRESH.
#
# The flow that matters happens in seconds: `show_day` writes, then `show_widget` opens the card, and its first
# fetch has to arrive already pointing at tomorrow (opening the widget can never select a day by itself, which
# is the whole defect). But a push kept forever would mean that reopening the agenda NEXT WEEK lands on a
# «tomorrow» that is now the past — a stale answer wearing the face of a deliberate one. Expiring it server-side
# is the one place with a trustworthy clock, and it costs the open widget nothing: when `view` goes away the
# token merely stops moving, so nothing snaps back and the operator's own tab survives.
_VIEW_TTL_S = 600


def _fresh_view(db: dict) -> dict | None:
    v = db.get("view") or None
    if not v:
        return None
    import time as _tm
    at = float(v.get("at") or 0)
    return v if at and (_tm.time() - at) <= _VIEW_TTL_S else None


def calendars() -> list[dict]:
    """Connection state of each calendar provider, for the header strip. Body in `gcal.py` (architecture
    ratchet extraction) — kept re-exported here since tests and `view_data()` call `data.calendars()`."""
    return gcal.calendars()


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
        # dated meetings -> full MONTH view (client-side calendar); a SERIES arrives as its days (V2-769)
        "meetings": recur.expand(db.get("meetings", []), _shift(-100), _shift(400)),
        "projects": db.get("projects", []),
        # The pushed VIEW (show_day). The widget honours it when its token moves and otherwise leaves the
        # operator's own tab alone — a refresh must never yank the day he is reading out from under him.
        "view": _fresh_view(db),
        # V2-686 — the pushed CONNECT screen: a voice order to link Google Calendar leaves the card on the
        # step that holds the button, because the consent itself needs the operator's own click.
        "connect": gcal.fresh_connect(db),
        "calendars": calendars(),        # header strip: which calendar providers are linked
        # V2-679 — the default-calendar picker reads this tick-refreshed cache; view_data stays a pure read.
        "googleCalendars": (db.get("google") or {}).get("calendars", []),
        "defaultCalendarId": (db.get("google") or {}).get("defaultCalendarId", ""),

        # V2-697 — appointments somebody ELSE asked for, waiting for the operator's yes. They are NOT in
        # `meetings`: nothing here is on his calendar yet, and painting one as an appointment would be the
        # claim this whole path exists to avoid making.
        "proposals": _proposals(),

        # V2-728 — work the SYSTEM will do at a given moment: «la semana que viene haz esto», «mírame esto
        # cada lunes». Operator, 2026-09-20: *«se puede ver perfectamente en la agenda, aunque es una tarea
        # no para nosotros, sino para el sistema»*. They are NOT meetings and never become one — nobody is
        # meeting anybody — so they travel in their own key and the render gives them their own mark.
        "systemTasks": _system_tasks(),

        # V2-744 — the TAREAS section: the operator's own lists, numbered as the screen numbers them.
        # Everything at once because a widget cannot fetch, so switching list is client-side.
        "tasks": tasklists.view(db),

        "warnings": plan.get("warnings", []),
        "coaching": plan.get("coaching", []),
    }


def _proposals() -> list[dict]:
    """Best-effort: an unreadable errand ledger costs the proposals band, never the calendar."""
    try:
        from nucleo.errands import proposals as _p
        return _p.pending()
    except Exception:  # noqa: BLE001
        return []


# The two views the brain reads of this card — WHAT CAN BE NAMED and WHAT IS INSIDE — live in
# `index.py` and must agree on what comes next (V2-707 F0). Re-exported: `refs` reads them here.
from .index import prompt_digest, ref_index  # noqa: F401,E402 — re-export


# A QUESTION is answered by SEARCHING, not by the summary below (`query.py`, V2-704).
from .query import read_query  # noqa: F401,E402 — re-export


# The SYSTEM's own timed work (V2-728) — extracted like `reminders.py`, re-exported as the known seam.
from .system_tasks import system_tasks as _system_tasks  # noqa: F401,E402 — re-export


# Relative spoken date/time normalization — extracted to `when.py` (V2-744, the 900-line ceiling).
# Re-exported under the historical private names: `invite.py`, `sweep.py` and this module's own tests
# reach them as `data._resolve_date` / `data._resolve_time`, and a rename would be a change nobody asked for.
from .when import _m2, _resolve_date, _resolve_time, _WEEKDAYS  # noqa: F401,E402 — re-export


# V2-643 — WHAT an appointment is made of, beyond a title and an hour. The operator's spec for a real
# calendar: «si son reuniones, si están confirmadas por la contraparte, si no; si es una cita con más
# personas, cuántas». So a meeting carries `attendees` (names), `status` (confirmed|pending), `location`
# and `category`, and the widget paints hue from the category and INTENSITY from the status — a pending
# invitation is outlined, a confirmed one is solid, exactly the convention every calendar already uses.
_STATUS = ("confirmed", "pending")
# WORD BOUNDARIES, not substrings, and PENDING is tested first — «sigue pendiente» read as confirmed
# because «si» lives inside «sigue» (caught by this module's own test before it shipped). A negated
# confirmation («sin confirmar», «no me lo ha confirmado») is pending, so it has to win the race.
def consent_scope(action: str, payload: dict | None = None) -> dict:
    """Which consent CLASS a call belongs to, when the manifest alone cannot say (V2-718).

    Read by `nucleo/flash/frontend._policy_key` before anything runs. The agenda has two calls whose
    friction depends on the CALL and not on the verb, and both were named by the operator: inviting
    somebody who is already in the meeting is free, inviting a third party is his to grant; moving an hour
    nobody else has committed to is free, moving one somebody else already agreed is his to grant.
    """
    try:
        from . import invite as _invite
        return _invite.consent_scope(str(action or ""), dict(payload or {}), load_db())
    except Exception:  # noqa: BLE001
        return {}


def radius(action: str, payload: dict | None = None) -> int | None:
    """How many appointments THIS call would delete (V2-720) — the widget counting its own rows, for the
    consent rule. The counting lives in `sweep.py`; this is the seam `frontend._scope` looks for."""
    try:
        return sweep.radius(str(action or ""), dict(payload or {}), load_db())
    except Exception:  # noqa: BLE001
        return None


# V2-778 F1-12 — the action handlers live in `actions.py`, imported back under their names (that module
# reads this one).
from .actions import (  # noqa: E402,F401
    _a_drop_project, _a_add_meeting, _a_dedupe_meetings, _a_cancel_meeting, _a_set_reminder, _a_clear_range,
    _a_clear_all, _a_move_meeting, _a_open_meeting, _a_update_meeting, _a_invite, _a_rsvp_meeting, _a_proposal,
    _a_show_day, _a_find_free, _a_connection, _a_add_meeting_noticed)
from . import reminders  # noqa: E402  (the asked notice, V2-781 T513)


# V2-778 F1-12 — one function per action (in `actions.py`), and `apply_action` is the table lookup. Each body
# is the branch it was, moved verbatim; a branch that used to fall through to the shared ending returns
# `_Continue(_extra)` instead, and the ending runs here as before. The contract gate reads the table's
# keys (`widgets/validator._table_actions`).
class _Continue:
    """An action that ends in the shared epilogue, carrying its `_extra`."""
    __slots__ = ("value",)

    def __init__(self, value):
        self.value = value


ACTIONS = {
    "drop_project": _a_drop_project,
    "add_meeting": _a_add_meeting_noticed,
    "dedupe_meetings": _a_dedupe_meetings,
    "cancel_meeting": _a_cancel_meeting,
    "set_reminder": _a_set_reminder,
    "clear_range": _a_clear_range,
    "clear_all": _a_clear_all,
    "move_meeting": _a_move_meeting,
    "open_meeting": _a_open_meeting,
    "close_meeting": _a_open_meeting,
    "update_meeting": _a_update_meeting,
    "invite": _a_invite,
    "rsvp_meeting": _a_rsvp_meeting,
    "accept_proposal": _a_proposal,
    "decline_proposal": _a_proposal,
    "show_day": _a_show_day,
    "find_free": _a_find_free,
    "connect": _a_connection,
    "disconnect": _a_connection,
    "set_default_calendar": _a_connection,
}


def apply_action(action: str, payload: dict | None = None) -> dict:
    """Widget actions (HANDOFF §9.3): mark done / not now / snooze / drop / replan. Mutates the isolated store."""
    if action == "move_meeting" and (payload or {}).get("day") and not payload.get("newDate"):
        payload = {**payload, "newDate": payload["day"]}   # in a move, a bare `day` is where it goes
        payload.pop("day")
    # A move is a write too: the model names its fields the way it names a meeting's (demo pass 2026-09-28, C4:
    # «move it half an hour later» → {date, start: 13:30, end: 14:15} refused as «no destination», and the next
    # turn re-sent the move instead of the Telegram he asked for).
    payload = recur.normalize(payload) if action in ("add_meeting", "update_meeting", "move_meeting") \
        else (payload or {})
    if action == "add_task" and payload.get("date") and any(payload.get(k) not in (None, "", False, True)
                                                             for k in reminders.ASK_KEYS):
        # V2-781 T515 — a dated task that asks for a NOTICE («estreno de Dexter, el 30, avísame») is an agenda
        # item: only an item carries a notice that is cancelled with it. Measured live: add_task {date, remind}
        # wrote a task, dropped the notice, and the reply promised it.
        return apply_action("add_meeting", payload)
    if action == "update_meeting" and any(str(payload.get(k) or "").strip() for k in edit.TIME_KEYS):
        # V2-770 — WHEN inside an edit («que dure hasta las cinco») is a reschedule: the door that owns the
        # notice takes it, then whatever else the edit said lands below. It was dropped here before.
        _moved = apply_action("move_meeting", payload)
        payload = {k: v for k, v in payload.items() if k not in edit.TIME_KEYS}
        if _moved.get("ok") is False or not (set(payload) - {"title", "date", "whole"}):
            return _moved
    db = load_db()
    _extra: dict = {}

    # V2-744 — every TASK verb, and the numbered lists they now live in, belong to `tasklists.py`. ONE
    # branch instead of five: «hecha» on a shopping item and «hecha» on a project task are the same verb,
    # and splitting them across two files is how the two halves drift apart.
    if action in tasklists.ACTIONS:
        res = tasklists.apply(action, payload, db)
        if not res.get("ok"):
            return res
        db["currentPlan"] = compute_plan(db)
        store.save(WIDGET_ID, db)
        return {**view_data(), **res}

    handler = ACTIONS.get(action) if isinstance(action, str) else None
    if handler is not None:
        _r = handler(action, payload, db, _extra)
        if not isinstance(_r, _Continue):
            return _r
        _extra = _r.value

    # 'replan' (and any action) just recomputes below
    db["currentPlan"] = compute_plan(db)  # persist the updated plan too, not just the mutation
    store.save(WIDGET_ID, db)   # persist the mutation; the plan is derived fresh in view_data()
    return {**view_data(), **{k: v for k, v in (_extra or {}).items() if v}}


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


def today_line(limit: int = 8) -> str:
    """TODAY's meetings as ONE compact block for the turn prompt, whether or not the card is open (V2-668b).

    Measured live (2026-09-11, 11:33, the very re-run of the Hacienda incident): with the agenda CLOSED, the
    STATE carried a memory pill the processor had distilled from the conversation — «cita con la agencia
    tributaria… a las 11:00» — while this widget held 11:30, and the model answered the pill without calling
    `read_widget`, which it had been offered. A widget-owned fact asserted by a recollection outranks the widget
    for a model, because the recollection is IN the prompt and the widget is a tool call away. So the one
    calendar everybody asks about every day rides in the state, and the block says who wins when they disagree.
    Only when there IS something today (an empty day costs nothing); the header names the precedence."""
    try:
        db = load_db()
        today = _today()
        meets = sorted(recur.on_date(db.get("meetings", []), today),
                       key=lambda m: (bool(not m.get("allDay")), str(m.get("startTime") or "")))
    except Exception:
        return ""
    if not meets:
        return ""
    rows = []
    for m in meets[:limit]:
        if m.get("allDay"):
            when = "todo el día"
        else:
            when = str(m.get("startTime") or "?") + (f"–{m['endTime']}" if m.get("endTime") else "")
        row = f"  {when} · {str(m.get('title') or 'Cita')[:80]}"
        if m.get("location"):
            row += f" · {str(m['location'])[:40]}"
        rows.append(row)
    if len(meets) > limit:
        rows.append(f"  … y {len(meets) - limit} más (read_widget agenda)")
    return ("AGENDA DE HOY — lo que GUARDA el widget agenda; si un recuerdo dice otra hora u otro día, MANDA esto "
            "(para otro día o más detalle: read_widget):\n" + "\n".join(rows))


def tick(ctx) -> None:
    """Background sync with Google Calendar (`widgets/background.py`'s scheduler contract needs this name in
    THIS file — the body lives in `gcal.py` to pay the architecture ratchet by extraction)."""
    from .reminders import roll_series
    roll_series(load_db, lambda db: store.save(WIDGET_ID, db))   # V2-769 — a series' notice moves on
    gcal.tick(ctx)


def on_calendar_connected() -> None:
    """Called by `connectors/calendar/server_api.py` right after OAuth consent completes. Body in `gcal.py`
    (same reason as `tick` above); kept re-exported here because that caller imports `widgets.agenda.data`."""
    gcal.on_calendar_connected()
