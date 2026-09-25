"""V2-770 — a scripted use case says fixed lines and grades each one against the widget's real state.

Measured live on the agenda (2026-09-25): 3 of 13 everyday operations landed while almost every reply said
«Hecho.». A transcript cannot tell those apart, so the catalogue of agenda operations is a SCRIPT whose steps
are read off the widget — and a red step fails the case whatever the judge scored.
"""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

from tests.use_cases.e2e.agent import dates, judge, scenarios, scripted, status


def _scn(script, locale="es"):
    return SimpleNamespace(id="x", locale=locale, script=script)


def _widget(monkeypatch, states):
    """Each read returns the next state (the last one repeats)."""
    seq = list(states)
    monkeypatch.setattr(scripted.probe_client, "widget_data", lambda wid, q="": seq.pop(0) if len(seq) > 1 else seq[0])
    monkeypatch.setattr(scripted.time, "sleep", lambda s: None)


def _dentist():
    thu = dt.date.today() + dt.timedelta(days=(3 - dt.date.today().weekday()) % 7 or 7)
    return {"meetings": [{"title": "Dentista", "date": thu.isoformat(), "startTime": "10:00"}]}


def test_both_agenda_cases_exist_and_every_step_names_a_real_check():
    ids = {s.id: s for s in scenarios.SCENARIOS}
    for sid in ("agenda-everyday-edits", "agenda-everyday-edits__us"):
        d = scripted.ScriptedDriver(ids[sid])
        assert len(d.steps) == 14
        assert all(not st.check or st.check in scripted.CHECKS for st in d.steps)


def test_the_script_never_carries_a_date_that_can_expire():
    d = scripted.ScriptedDriver(next(s for s in scenarios.SCENARIOS if s.id == "agenda-everyday-edits"))
    assert all("{" not in st.say for st in d.steps)
    assert str(dates.tuesday_after_next().day) in d.steps[9].say


def test_a_landed_step_is_green_and_the_next_line_is_said(monkeypatch):
    _widget(monkeypatch, [_dentist()])
    d = scripted.ScriptedDriver(_scn((("Apúntame el dentista", "agenda.dentist_next_thursday_10"),
                                      ("Y otra cosa", ""))))
    assert d.opening() == "Apúntame el dentista"
    d.hears("Hecho.")
    assert d.reply() == "Y otra cosa"
    assert d.results[0]["ok"] is True


def test_a_claim_over_an_untouched_store_is_red(monkeypatch):
    _widget(monkeypatch, [{"meetings": []}])
    _real = scripted.check
    monkeypatch.setattr(scripted, "check", lambda name, **kw: _real(name, wait_s=0))
    d = scripted.ScriptedDriver(_scn((("Apúntame el dentista", "agenda.dentist_next_thursday_10"),)))
    d.opening()
    d.hears("Hecho.")
    d.reply()
    assert d.done and d.results[0]["ok"] is False
    assert scripted.failed(d.results)


def test_a_question_back_gets_one_yes_before_the_check_is_read_again(monkeypatch):
    said_yes = {"v": False}
    monkeypatch.setattr(scripted.probe_client, "widget_data",
                        lambda wid, q="": _dentist() if said_yes["v"] else {"meetings": []})
    monkeypatch.setattr(scripted, "check", lambda name, **kw: (bool(said_yes["v"]), ""))
    d = scripted.ScriptedDriver(_scn((("Apúntame el dentista", "agenda.dentist_next_thursday_10"),
                                      ("Gracias", ""))))
    d.opening()
    d.hears("¿Te lo apunto el jueves a las diez?")
    assert d.reply() == "Sí, adelante."
    said_yes["v"] = True
    d.hears("Hecho.")
    assert d.reply() == "Gracias"
    assert d.results[0]["ok"] is True and d.results[0]["answered_yes"] is True


def test_a_write_that_lands_a_moment_after_the_reply_is_waited_for(monkeypatch):
    _widget(monkeypatch, [{"meetings": []}, {"meetings": []}, _dentist()])
    ok, _why = scripted.check("agenda.dentist_next_thursday_10", wait_s=5)
    assert ok is True


def test_an_unreadable_widget_is_not_a_pass(monkeypatch):
    _widget(monkeypatch, [None])
    ok, why = scripted.check("agenda.dentist_next_thursday_10", wait_s=0)
    assert ok is None and "could not be read" in why
    assert scripted.failed([{"check": "agenda.x", "ok": None}])


def _row(steps, overall=5):
    return {"scenario": "agenda-everyday-edits", "run": {"mechanism_report": {"script_checks": steps},
                                                        "transcript": [{"who": "tester"}, {"who": "zaelar",
                                                                                           "text": "Hecho."}]},
            "verdict": {"overall": overall, "scores": {"mecanismo": 5}}}


def test_one_red_step_fails_the_case_whatever_the_judge_scored():
    steps = [{"step": 1, "check": "agenda.a", "ok": True}, {"step": 2, "check": "agenda.b", "ok": False}]
    assert status._state(5, _row(steps)) == "FAIL"
    assert status._state(5, _row([{"step": 1, "check": "agenda.a", "ok": True}])) == "PASS"


def test_the_judge_is_told_which_steps_are_red():
    txt = judge.mechanism_facts({"script_checks": [{"step": 3, "said": "Vale, ya la puedes cerrar",
                                                    "check": "agenda.card_closed", "ok": False}]})
    assert "GUION" in txt and "agenda.card_closed" in txt and "1 en ROJO" in txt


def test_the_sandbox_is_pinned_to_the_case_language_before_it_boots(tmp_path):
    """The preflight's «di solo: ok» locked Italian twice and a Spanish round answered in English."""
    from tests.use_cases.e2e.agent import run
    run.seed_language(tmp_path, "es")
    import json
    assert json.loads((tmp_path / "config" / "settings.json").read_text())["stt_language"] == "es"


def test_the_judge_is_told_an_empty_agenda_after_a_deleting_script_is_expected():
    txt = judge.mechanism_facts({"script_checks": [{"step": 1, "check": "agenda.a", "ok": True}]})
    assert "ÚLTIMO paso" in txt
