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
from . import edit, planner, recur, series, tasklists
from widgets.agenda import task_read as _task_read_m


# `_strip_accents` lives with the spoken-date resolver (V2-744); re-exported because tests reach it here.
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
    # v1 → v2 (V2-744): tasks live in NUMBERED LISTS; a task without a `listId` joins «General» (`task_read.migrate`).
    return _task_read_m.migrate(db)


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


# The text views: the spoken line, the coach context, today's block.
from .digest import _spoken, coach_context, today_line  # noqa: E402,F401 — re-export


def _lang() -> str:
    """Active engine language code — V2-639: the plan speaks the operator's language."""
    from i18n import langs as _langs
    return (_langs.current_code() or "en").lower()


def compute_plan(db: dict | None = None) -> dict:
    # PURE: derive the day plan; do NOT persist on read (avoids read-modify-write races; GET stays idempotent).
    return planner.plan_day(db or load_db(), date=_today(), now=_now(), lang=_lang())


# The pieces view_data() assembles: horizon, pushed-view freshness, proposals.
from .view import _VIEW_TTL_S, _fresh_view, _horizon, _proposals  # noqa: E402,F401 — re-export


def calendars() -> list[dict]:
    """Connection state of each calendar provider, for the header strip (body in `gcal.py`)."""
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
        "calendars": calendars(),        # header strip: which calendar providers are linked
        # V2-679 — the default-calendar picker reads this tick-refreshed cache; view_data stays a pure read.
        "googleCalendars": (db.get("google") or {}).get("calendars", []),
        "defaultCalendarId": (db.get("google") or {}).get("defaultCalendarId", ""),

        # Appointments somebody ELSE asked for, awaiting the operator's yes — NOT in `meetings`: none is on
        # his calendar yet (V2-697).
        "proposals": _proposals(),

        # Work the SYSTEM will do at a given moment («every Monday check this»). NOT meetings and never become
        # one: their own key and their own mark (V2-728).
        "systemTasks": _system_tasks(),

        # The TAREAS section: the operator's lists, numbered as the screen numbers them; all at once because a
        # widget cannot fetch (V2-744).
        "tasks": _task_read_m.view(db),

        "warnings": plan.get("warnings", []),
        "coaching": plan.get("coaching", []),
    }



# The two views the brain reads of this card — WHAT CAN BE NAMED and WHAT IS INSIDE — live in
# `index.py` and must agree on what comes next (V2-707 F0). Re-exported: `refs` reads them here.
from .index import prompt_digest, ref_index  # noqa: F401,E402 — re-export


# A QUESTION is answered by SEARCHING, not by the summary below (`query.py`, V2-704).
from .query import read_query  # noqa: F401,E402 — re-export


# The SYSTEM's own timed work (V2-728) — extracted like `reminders.py`, re-exported as the known seam.
from .system_tasks import system_tasks as _system_tasks  # noqa: F401,E402 — re-export


# Relative spoken date/time normalization lives in `when.py` (V2-744); re-exported because `invite.py`,
# `sweep.py` and the tests reach `data._resolve_date` / `data._resolve_time`.
from .when import _m2, _resolve_date, _resolve_time, _WEEKDAYS  # noqa: F401,E402 — re-export


# A meeting carries `attendees`, `status` (confirmed|pending), `location` and `category`; the widget paints hue
# from the category and INTENSITY from the status — pending outlined, confirmed solid (V2-643). The spoken status
# is parsed in `details.py` on WORD BOUNDARIES with PENDING first, so a negated confirmation stays pending.
_STATUS = ("confirmed", "pending")
def consent_scope(action: str, payload: dict | None = None) -> dict:
    """Which consent CLASS a call belongs to, when the manifest alone cannot say (V2-718).

    Read by `nucleo/flash/frontend._policy_key` before anything runs. Two calls depend on the CALL, not the verb:
    inviting someone already in the meeting is free, a third party is his to grant; moving an hour nobody else
    committed to is free, one somebody already agreed is his to grant.
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


# The action handlers live in `actions.py` (which reads this module) (V2-778 F1-12).
from .actions import (  # noqa: E402,F401
    _a_drop_project, _a_add_meeting, _a_dedupe_meetings, _a_cancel_meeting, _a_clear_range, _a_clear_all,
    _a_move_meeting, _a_update_meeting, _a_restore_meeting)
from .meeting_views import (  # noqa: E402,F401
    _a_open_meeting, _a_invite, _a_rsvp_meeting, _a_proposal, _a_show_day, _a_find_free, _a_connection)
from .notice_actions import _a_set_reminder, _a_add_meeting_noticed  # noqa: E402,F401
from . import reminders  # noqa: E402  (the asked notice, V2-781 T513)
from .notice import _a_add_reminder  # noqa: E402  (a notice with no appointment, refactor2710-06)


# `apply_action` is a table lookup; a handler that ends in the shared epilogue returns `_Continue(_extra)`. The
# contract gate reads the table's keys (`widgets/validator._table_actions`).
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
    "add_reminder": _a_add_reminder,
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
    "restore_meeting": _a_restore_meeting,
    "set_default_calendar": _a_connection,
}


def apply_action(action: str, payload: dict | None = None) -> dict:
    """Widget actions (HANDOFF §9.3): mark done / not now / snooze / drop / replan. Mutates the isolated store."""
    if action == "move_meeting" and (payload or {}).get("day") and not payload.get("newDate"):
        payload = {**payload, "newDate": payload["day"]}   # in a move, a bare `day` is where it goes
        payload.pop("day")
    # A move is a write too: the model names its fields the way it names a meeting's ({date, start, end}).
    payload = series.normalize(payload) if action in ("add_meeting", "update_meeting", "move_meeting") \
        else (payload or {})
    if action in ("move_meeting", "update_meeting", "cancel_meeting", "open_meeting"):
        payload = edit.day_out_of_title(payload)       # «Piano del martes 2026-10-13» names that day (V2-781)
    if action == "add_task" and payload.get("date") and any(payload.get(k) not in (None, "", False, True)
                                                             for k in reminders.ASK_KEYS):
        # A dated task that asks for a NOTICE is an agenda item: only an item carries a notice that is cancelled
        # with it (V2-781 T515).
        return apply_action("add_meeting", payload)
    if action == "update_meeting" and any(str(payload.get(k) or "").strip() for k in edit.TIME_KEYS):
        # WHEN inside an edit is a reschedule: the door that owns the notice takes it, the rest lands below (V2-770).
        _moved = apply_action("move_meeting", payload)
        payload = {k: v for k, v in payload.items() if k not in edit.TIME_KEYS}
        if _moved.get("ok") is False or not (set(payload) - {"title", "date", "whole"}):
            return _moved
    db = load_db()
    _extra: dict = {}

    # Every TASK verb belongs to `tasklists.py`, in ONE branch: «done» on a shopping item and on a project task is
    # the same verb (V2-744).
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



def tick(ctx) -> None:
    """Background sync with Google Calendar (the scheduler contract needs this name in THIS file; body in `gcal.py`)."""
    from .reminders import roll_series
    roll_series(load_db, lambda db: store.save(WIDGET_ID, db))   # V2-769 — a series' notice moves on
    gcal.tick(ctx)


def on_calendar_connected() -> None:
    """Called by `connectors/calendar/server_api.py` right after OAuth consent completes (body in `gcal.py`)."""
    gcal.on_calendar_connected()
