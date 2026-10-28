#
# Agenda widget — the pieces `view_data()` assembles beyond the plan: the day horizon, the pushed view's
# freshness and the pending proposals. Moved out of `data.py` (refactor2710-12 T-03), which re-exports them.
# `_today`, `_now`, `_lang` and `_VIEW_TTL_S` are read back through `data`, where tests patch them.
#
from . import planner


def _horizon(db: dict, span: int = 7) -> list[dict]:
    """Per-day plans for TODAY .. TODAY+span-1, so the widget exposes a time horizon (not only today) and
    switches views client-side without another request (widget.js cannot fetch). `plan_day` is pure and cheap."""
    import time as _t
    today = _d._today()
    base = _t.mktime(_t.localtime())
    lang = _d._lang()
    from i18n import langs as _langs
    wk = _langs.words("agenda.week_labels", code=lang[:2] or None, default=())
    words = _langs.words("agenda.day_words", code=lang[:2] or None, default=())
    out: list[dict] = []
    for i in range(span):
        d = _t.localtime(base + i * 86400)
        date = _t.strftime("%Y-%m-%d", d)
        plan = planner.plan_day(db, date=date, now=_d._now() if date == today else "", lang=lang)
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
    return v if at and (_tm.time() - at) <= _d._VIEW_TTL_S else None


def _proposals() -> list[dict]:
    """Best-effort: an unreadable errand ledger costs the proposals band, never the calendar."""
    try:
        from nucleo.errands import proposals as _p
        return _p.pending()
    except Exception:  # noqa: BLE001
        return []


from widgets.agenda import data as _d  # noqa: E402 — the facade, read at call time
