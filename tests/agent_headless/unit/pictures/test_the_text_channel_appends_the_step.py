"""The text channel's reply door appends the step line — the brief reaches `delivery.apply_to_reply` (2.505).

The voice channel is left out on purpose (its stream is already said when a backstop could act, V2-210); the text
channel's one door for a waiting reply is `delivery.apply_to_reply`, and it only knows he wants to be told if it
is handed the turn brief.
"""
from __future__ import annotations

from nucleo import dispatch
from nucleo.flash import delivery, live_blocks, step_line

from ._brief import brief


def test_a_waiting_reply_goes_out_with_the_step(monkeypatch):
    step_line.forget()
    monkeypatch.setattr(live_blocks, "any_live_task_rows", lambda n: ("", []))
    monkeypatch.setattr(live_blocks, "any_stalled_task", lambda: ("", 0, ""))
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [
        {"id": "2", "uid": "u", "goal": "Verified Amalfi photos", "title": "Ferrari Amalfi official photos",
         "phase": "going into media.ferrari.com", "note": "", "plan": [], "done": 0, "waiting_on": ""}])
    monkeypatch.setattr("i18n.langs.current_code", lambda: "en")   # an English instance wrote its phase in English
    out = delivery.apply_to_reply("Will do — I'll come back to you.", [], heard_now="ok, keep me posted",
                                  brief=brief(wants_words="tell"))
    assert out.startswith("Will do") and "going into media.ferrari.com" in out, out
    step_line.forget()
