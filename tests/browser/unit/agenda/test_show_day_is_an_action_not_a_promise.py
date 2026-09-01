"""V2-540 — changing the day the agenda SHOWS is an action, because otherwise it is a promise.

From the operator's own session (2026-09-01, 15:11). He had just had an appointment added for tomorrow and
asked to see that day. The observability of those three turns, verbatim from `events`:

    15:11:17  widget/show agenda   ← «show por backstop de promesa (prometió mostrar sin tool)»
              reply: «Mañana miércoles día 2 tienes a las 8:00 … ¿Quieres que te la abra en pantalla?»
    15:11:32  widget/show agenda   ← «show por guard determinista (tool espuria evitada)»
              reply: «Te abro la agenda con la vista de mañana.»
    15:11:47  widget/move agenda   (src: user — he moved the card himself)
              reply: «Abro la agenda en pantalla ahora mismo, con la vista de mañana miércoles.»

Three promises of «la vista de mañana» and three bare `show:agenda`, which opens on TODAY. The model was not
disobeying and was not hallucinating a result: the day tabs were DOM state inside `widget.js` (`el._agSel`) with
no name in `manifest.json`, so there was no wrong tool to choose — there was NO tool. An undeclared capability
is not one the model can decline; it is one it will narrate.

`add_meeting` in that same session worked first time. The difference between the two is this file.
"""
from __future__ import annotations

import json
import pathlib

import pytest

ENGINE = pathlib.Path(__file__).resolve().parents[4]


@pytest.fixture
def agenda(tmp_path, monkeypatch):
    """ISOLATED store — never the operator's real agenda."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.agenda import data as ag
    return ag


def _today_and_tomorrow(ag):
    days = ag.view_data()["days"]
    return days[0]["date"], days[1]["date"]


def test_the_action_EXISTS_in_the_manifest_or_the_model_cannot_choose_it(agenda):
    """The root cause, stated as a check. `apply_action` handling `show_day` while the manifest stays quiet
    would fix nothing: the manifest IS the vocabulary the FlashBrain gets to pick from."""
    m = json.loads((ENGINE / "widgets" / "agenda" / "manifest.json").read_text(encoding="utf-8"))
    assert "show_day" in m["actions"], "the day tabs are unreachable by voice again"
    desc = m["actions"]["show_day"]["desc"].lower()
    assert "mañana" in desc, "the model needs the everyday phrasing, not a schema"
    assert "day" in m["actions"]["show_day"]["payload"], m["actions"]["show_day"]


def test_the_manifest_says_that_SHOWING_the_widget_cannot_do_this(agenda):
    """The specific confusion that produced the bug: the brain reached for `show_widget` and believed the day
    came with it. The usage text has to close that door in words, where the model reads."""
    m = json.loads((ENGINE / "widgets" / "agenda" / "manifest.json").read_text(encoding="utf-8"))
    txt = (m["usage"] + m["actions"]["show_day"]["desc"]).lower()
    assert "hoy" in txt and ("abrir" in txt or "abre" in txt or "mostrar" in txt), txt


@pytest.mark.parametrize("spoken", ["mañana", "Mañana miércoles", "manana"])
def test_tomorrow_however_he_says_it_selects_TOMORROW(agenda, spoken):
    _, tomorrow = _today_and_tomorrow(agenda)
    res = agenda.apply_action("show_day", {"day": spoken})
    assert res["view"]["sel"] == tomorrow, res["view"]


def test_today_the_day_after_and_a_weekday_all_resolve(agenda):
    today, tomorrow = _today_and_tomorrow(agenda)
    days = agenda.view_data()["days"]
    assert agenda.apply_action("show_day", {"day": "hoy"})["view"]["sel"] == today
    assert agenda.apply_action("show_day", {"day": "pasado mañana"})["view"]["sel"] == days[2]["date"]
    assert agenda.apply_action("show_day", {"day": "2026-12-24"})["view"]["sel"] == "2026-12-24"


def test_week_and_month_are_views_not_dates(agenda):
    assert agenda.apply_action("show_day", {"day": "la semana"})["view"]["sel"] == "week"
    assert agenda.apply_action("show_day", {"day": "vista de mes"})["view"]["sel"] == "month"


def test_the_token_MOVES_every_time_even_for_the_same_day(agenda):
    """Why the push carries a counter and not just the day. Tomorrow → he clicks back to today himself →
    «mañana» again: with the day as the token, that second ask writes an identical value, changes no JSON
    signature, re-renders nothing and moves nothing — this very bug wearing another mask."""
    a = agenda.apply_action("show_day", {"day": "mañana"})["view"]
    b = agenda.apply_action("show_day", {"day": "mañana"})["view"]
    assert a["sel"] == b["sel"] and b["n"] > a["n"], (a, b)


def test_showing_a_day_CHANGES_NOTHING_the_operator_owns(agenda):
    """It moves what is on screen and not one appointment, task or project. A view action that mutated data
    would be a far worse bug than the one it fixes."""
    db = agenda.load_db()
    db["meetings"] = [{"title": "Traumatólogo", "date": "2026-09-02",
                       "startTime": "08:00", "endTime": "09:00"}]
    db["tasks"] = [{"id": "t1", "title": "Revisar", "status": "todo"}]
    from widgets import store
    store.save(agenda.WIDGET_ID, db)
    agenda.apply_action("show_day", {"day": "mañana"})
    after = agenda.load_db()
    assert after["meetings"] == db["meetings"] and after["tasks"] == db["tasks"]


def test_a_stale_push_is_NOT_served_to_a_widget_that_opens_days_later(agenda, monkeypatch):
    """A push kept forever means reopening the agenda next week lands on a «tomorrow» that is now the past —
    a stale answer wearing the face of a deliberate one. The clock lives on the server, and expiring it costs
    an OPEN widget nothing: `view` simply stops arriving, the token stops moving, nothing snaps back."""
    agenda.apply_action("show_day", {"day": "mañana"})
    assert agenda.view_data()["view"] is not None
    monkeypatch.setattr(agenda, "_VIEW_TTL_S", -1)
    assert agenda.view_data()["view"] is None, "a week-old view is still being pushed at a fresh mount"


# ── The header's calendar connectors (the operator's second ask on the same widget) ──────────────────────────

def test_the_connector_strip_READS_the_inventory_instead_of_declaring_a_state(agenda, monkeypatch):
    """It must be a seam, not a hardcoded «off». The day a calendar connector registers under this family it
    lights up here with nothing else to change — and that is the only thing that makes the strip worth having
    instead of three painted decorations."""
    from connectors import registry
    monkeypatch.setattr(registry, "descriptors", lambda: [
        {"id": "google", "label": "Google Calendar", "family": "calendar", "connected": True},
    ])
    by_id = {c["id"]: c for c in agenda.calendars()}
    assert by_id["google"]["status"] == "connected", by_id["google"]
    assert by_id["icloud"]["status"] == "unavailable", by_id["icloud"]


def test_TODAY_it_says_none_is_built_because_none_is(agenda):
    """`connectors/` holds six connectors and not one is a calendar (INI-027). «You have not linked it» and «we
    have not built it» are different sentences, and showing the first when the second is true is the same class
    of lie as promising a view — which is the other half of this very file."""
    cals = agenda.calendars()
    assert [c["id"] for c in cals] == ["google", "icloud", "caldav"], cals
    assert all(c["status"] == "unavailable" for c in cals), cals


def test_a_registry_that_cannot_be_read_is_not_a_connected_calendar(agenda, monkeypatch):
    """Fail-CLOSED. A broken read must never brighten an icon: the whole point of the strip is that its
    brightness can be trusted."""
    from connectors import registry
    def _boom():
        raise RuntimeError("registry unavailable")
    monkeypatch.setattr(registry, "descriptors", _boom)
    assert all(c["status"] == "unavailable" for c in agenda.calendars())
