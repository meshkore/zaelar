"""The text channel's reply door appends the step line — the brief reaches `delivery.apply_to_reply` (2.505).

The voice channel is left out on purpose (its stream is already said when a backstop could act, V2-210); the text
channel's one door for a waiting reply is `delivery.apply_to_reply`, and it only knows he wants to be told if the
probe hands it the turn brief.
"""
from __future__ import annotations

import inspect

from nucleo import dispatch
from nucleo.flash import delivery, live_blocks, probe, step_line

from ._brief import brief


def test_the_probe_passes_its_brief():
    assert "apply_to_reply(spoken, sess.window, heard_now=operator_text or text, brief=_tbrief)" in \
        inspect.getsource(probe.run_turn)


def test_a_waiting_reply_goes_out_with_the_step(monkeypatch):
    step_line.forget()
    monkeypatch.setattr(live_blocks, "any_live_task_rows", lambda n: ("", []))
    monkeypatch.setattr(live_blocks, "any_stalled_task", lambda: ("", 0, ""))
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [
        {"id": "2", "uid": "u", "goal": "Verified Amalfi photos", "title": "Ferrari Amalfi official photos",
         "phase": "entrando en media.ferrari.com", "note": "", "plan": [], "done": 0, "waiting_on": ""}])
    monkeypatch.setattr("i18n.langs.current_code", lambda: "en")
    out = delivery.apply_to_reply("Will do — I'll come back to you.", [], heard_now="ok, keep me posted",
                                  brief=brief(wants_words="tell"))
    assert out.startswith("Will do") and "going into media.ferrari.com" in out, out
    step_line.forget()
