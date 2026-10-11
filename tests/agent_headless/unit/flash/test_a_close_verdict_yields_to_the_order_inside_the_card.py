"""A sure «close» verdict yields to the order INSIDE the card it would close (agenda-everyday-edits ES, 2026-10-11).

Two red steps, one class. «Vale, ya la puedes cerrar» (the dentist's detail open) read canvas=close 1.00 AND
`agenda:close_meeting` 1.00; «Y quita el piano entero, toda la serie» read canvas=close 0.91 AND
`agenda:cancel_meeting` 0.71. The model called nothing and said «Hecho.»; the canvas completion
(`direct_action.complete_canvas`, both channels) ran FIRST and closed the whole agenda — the detail stayed «open»
in the card's state and six piano lessons stayed in the calendar. `canvas_yields` (V2-781 pair 5) already said a
sure inner op wins, but only at the data completion, which the canvas completion pre-empted.

Nodes: 2.440 a sure inner op wins over the close (both channels); 2.441 an inner WRITE is never read as a close
and is left to the repair; 2.442 a named card and an unsure inner lens keep the close (R4 / M4); 2.443 the claim
backing cancels the WHOLE series he named by one word; 2.444 the rename field is named as the NEW title.
"""
from __future__ import annotations

import json
import pathlib
import time

import pytest

from nucleo.flash import card_close as CC
from nucleo.flash import direct_action as DA
from nucleo.flash import verdict_card as VC

ENGINE = pathlib.Path(__file__).resolve().parents[4]


@pytest.fixture
def verdict(monkeypatch):
    """The brief's two answers, set per test: the canvas gesture and the inner action with its confidence."""
    st = {"canvas": "close", "action": ("agenda", "close_meeting"), "conf": 1.0, "named": [], "tags": []}
    monkeypatch.setattr(DA, "sure_canvas", lambda b: st["canvas"])
    monkeypatch.setattr(DA, "from_brief", lambda b: st["action"])
    monkeypatch.setattr(DA, "_action_sure", lambda b, floor=0.8: st["conf"] >= floor)
    monkeypatch.setattr(DA, "named_cards", lambda text: list(st["named"]))
    return st


def _canvas(st, said):
    return DA.complete_canvas(object(), tag_emit=lambda a, x: st["tags"].append((a, x)), emit=lambda *a, **k: None,
                              operator_text=said)


# ── 2.440 · a sure inner op wins over the close — in both channels ────────────────────────────────────────────

def test_the_measured_close_of_the_detail_does_not_close_the_agenda(verdict):
    assert VC.inner_order_wins(object(), "Vale, ya la puedes cerrar") == "sure"
    assert _canvas(verdict, "Vale, ya la puedes cerrar") == "" and verdict["tags"] == []


def test_the_text_channel_runs_the_inner_close_in_its_place(verdict, monkeypatch):
    monkeypatch.setattr(DA, "resolve", lambda *a, **k: {"widget": "agenda", "action": "close_meeting", "payload": {},
                                                        "label": "agenda:close_meeting", "source": "no-payload"})
    calls: list = []
    got = CC.complete_canvas_mirror(object(), "Vale, ya la puedes cerrar", blocked=False, calls=calls)
    assert got == {"action": "widget_data", "spoken": "", "_already": True}
    assert [(c["args"]["widget_id"], c["args"]["action"]) for c in calls] == [("agenda", "close_meeting")]


def test_a_payload_read_from_a_whole_sentence_is_left_to_the_repair(verdict, monkeypatch):
    monkeypatch.setattr(DA, "resolve", lambda *a, **k: {"widget": "agenda", "action": "cancel_meeting",
                                                        "payload": {"title": "quita el piano"}, "label": "x",
                                                        "source": "operator-words"})
    verdict["action"] = ("agenda", "cancel_meeting")
    calls: list = []
    assert CC.inner_order_mirror(object(), "quita el piano", calls, emit=lambda *a, **k: None) == {} and calls == []


# ── 2.441 · an inner WRITE is never read as a close ───────────────────────────────────────────────────────────

def test_the_measured_series_removal_does_not_close_the_agenda(verdict):
    verdict.update(action=("agenda", "cancel_meeting"), conf=0.71)
    said = "Y quita el piano entero, toda la serie"
    assert VC.inner_order_wins(object(), said) == "write"
    assert _canvas(verdict, said) == "" and verdict["tags"] == []
    assert VC.close_is_owed(object(), said) is False          # the voice promise door does not close it either
    assert VC.canvas_yields(object()) is False                # …and the bare data rung does not guess its payload


def test_both_channels_ask_the_same_rule():
    src = (ENGINE / "nucleo/flash/direct_action.py").read_text(encoding="utf-8")
    assert ".inner_order_wins(brief, operator_text)" in src
    assert "_vcard.close_is_owed(_brief, _op_text)" in (ENGINE / "nucleo/flash/post_stream_words.py").read_text(
        encoding="utf-8")
    assert "complete_canvas_mirror(_tbrief, operator_text, blocked=action != \"chat\" or bool(tool_calls or tags), " \
           "calls=tool_calls)" in (ENGINE / "nucleo/flash/probe_mirrors.py").read_text(encoding="utf-8")


# ── 2.442 · the close stands when he named a card, or the inner op is an unsure lens ──────────────────────────

def test_a_card_he_named_keeps_the_close(verdict):
    verdict.update(action=("agenda", "cancel_meeting"), conf=0.71, named=["agenda"])
    assert VC.inner_order_wins(object(), "quita la agenda") == ""


def test_an_unsure_inner_lens_keeps_the_close(verdict):
    verdict["conf"] = 0.55                                    # M4: «ok close that» meant the chart
    assert VC.inner_order_wins(object(), "ok close that") == ""
    assert VC.close_is_owed(object(), "ok close that") is True


def test_no_sure_close_no_question(verdict):
    verdict.update(canvas="", action=("agenda", "cancel_meeting"))
    assert VC.inner_order_wins(object(), "quita el piano") == ""


# ── 2.443 · the claim backing cancels the whole series he named by one word ───────────────────────────────────

def _agenda():
    series = {"freq": "weekly", "interval": 1, "until": "2026-11-30", "days": [1]}
    return {"meetings": [{"title": "Clase de piano de Abril", "date": "2026-10-27", "startTime": "17:00",
                          "repeat": series},
                         {"title": "Clase de piano de Abril", "date": "2026-10-14", "startTime": "17:00",
                          "fromSeries": "2026-10-13"},
                         {"title": "Revisión dental con el doctor Ruiz", "date": "2026-10-15", "startTime": "11:30"}]}


def test_the_measured_hecho_over_the_series_cancels_all_of_it():
    from nucleo.flash import agenda_claims as ac
    got = ac.cancel_call("Y quita el piano entero, toda la serie", "Hecho.", _agenda(), now=time.time())
    assert got == {"widget_id": "agenda", "action": "cancel_meeting",
                   "payload": {"title": "Clase de piano de Abril", "whole": True}}


def test_the_english_whole_series_too():
    from nucleo.flash import agenda_claims as ac
    db = _agenda()
    for m in db["meetings"][:2]:
        m["title"] = "Abril's piano lesson"
    got = ac.cancel_call("And get rid of the piano completely, the whole series", "Done.", db, now=time.time())
    assert got and got["payload"] == {"title": "Abril's piano lesson", "whole": True}


def test_a_series_named_without_its_scope_keeps_its_question():
    from nucleo.flash import agenda_claims as ac
    got = ac.cancel_call("Quita el piano", "Hecho.", _agenda(), now=time.time())
    assert got and got["payload"] == {"title": "Clase de piano de Abril"}


def test_one_word_two_titles_names_nothing():
    from nucleo.flash import agenda_claims as ac
    db = _agenda()
    db["meetings"].append({"title": "Concierto de piano", "date": "2026-10-30", "startTime": "20:00"})
    assert ac.cancel_call("Quita el piano", "Hecho.", db, now=time.time()) is None


# ── 2.444 · the rename field reads as the NEW title, the selector as the current one ──────────────────────────

def test_the_rename_field_is_the_new_title():
    spec = json.loads((ENGINE / "widgets/agenda/manifest.json").read_text(encoding="utf-8"))
    pay = spec["actions"]["update_meeting"]["payload"]
    assert "NUEVO" in pay["newTitle"] and "ACTUAL" in pay["title"]
