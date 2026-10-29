"""A claim about somebody else's answer needs a SOURCE (V2-831 T-19 pass 9, Z1).

«What's on my plate tomorrow»: «the catch-up with <friend> at four thirty isn't confirmed by him yet». Nobody had asked
him. The row was `{attendees: [<friend>], status: pending}` — the agenda's DEFAULT for any meeting with people (V2-642,
which keeps its outlined paint) — and the digest wrote it as «SIN confirmar por la otra parte», which the model said.
The default is now marked `status_by: default`: the paint still reads it, but the digest, the model-facing read and the
detail card state the other side's answer only when it was stated (his words, `update_meeting`) or synced. Any card
reading the row, any language.
"""
from __future__ import annotations

import time

import pytest

from widgets.agenda import data as agenda, index, query
from tests.browser.unit.agenda.test_the_agenda_looks_like_a_calendar import _data, _meet, _mount, _page  # noqa: F401


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    from widgets import store
    from nucleo.pulse import scheduler
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(scheduler, "create", lambda prompt, stamp, name="", origin="cron": {"ok": True, "id": "j"})
    monkeypatch.setattr(scheduler, "cancel", lambda ref: True)


def _tomorrow() -> str:
    return time.strftime("%Y-%m-%d", time.localtime(time.time() + 86400))


def test_the_digest_and_the_read_say_nothing_about_a_default_answer():
    agenda.apply_action("add_meeting", {"title": "Catch up with Rowan", "date": _tomorrow(), "startTime": "16:30",
                                        "attendees": ["Rowan"]})
    m = agenda.load_db()["meetings"][0]
    assert m["status"] == "pending" and m["status_by"] == "default"      # the paint keeps V2-642's outline
    assert "confirm" not in index.prompt_digest().lower(), index.prompt_digest()
    assert "confirm" not in query._row(m).lower(), query._row(m)


def test_the_digest_and_the_read_say_a_stated_answer():
    agenda.apply_action("add_meeting", {"title": "Catch up with Rowan", "date": _tomorrow(), "startTime": "16:30",
                                        "attendees": ["Rowan"]})
    agenda.apply_action("update_meeting", {"title": "catch up with rowan", "status": "sigue sin confirmar"})
    m = agenda.load_db()["meetings"][0]
    assert "status_by" not in m and "SIN confirmar por la otra parte" in query._row(m)
    assert "SIN confirmar por la otra parte" in index.prompt_digest()
    agenda.apply_action("update_meeting", {"title": "catch up with rowan", "status": "ya me lo ha confirmado"})
    assert "confirmada" in query._row(agenda.load_db()["meetings"][0])


def test_the_detail_card_states_their_answer_only_from_a_source(_page):  # noqa: F811
    _mount(_page, _data(meetings=[_meet("Catch up", start="16:00", end="17:00", attendees=["Rowan"],
                                        status="pending", status_by="default")]))
    _page.click(".agev")
    assert _page.locator(".agpanel .agpstate").count() == 0, "a default is nobody's answer: no «Confirmada», no «Sin confirmar»"
    _mount(_page, _data(meetings=[_meet("Catch up", start="16:00", end="17:00", attendees=["Rowan"], status="pending")]))
    _page.click(".agev")
    assert _page.locator(".agpanel .agpstate.pending").count() == 1
