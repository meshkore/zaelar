"""A message that cites a meeting carries the AGENDA's time, not the model's memory (V2-776 K1, 2026-09-29).

Demo pass 56, C3-C5: «ok book it» booked 16:00-16:45, «move it half an hour later» moved it to 16:30, «send
ethan a telegram with the new time» → the model wrote «our catch-up tomorrow is now at 5:00 PM» and a real
Telegram went out with a false time. Nothing tied a clock time in an outgoing text to the meeting the
conversation was about. Deterministic, no new model pass: the last agenda mutation of the window names the
meeting, the text names it too (a shared word), and the time in the text is the agenda's — rewritten when it is
not. Never a question: he asked to send.
"""
import asyncio
import pathlib

from nucleo.flash import meeting_time as mt

ENGINE = pathlib.Path(__file__).resolve().parents[3]
MEETING = {"id": "m1", "title": "Catch up with Ethan", "date": "2026-09-30", "startTime": "16:30", "endTime": "17:15"}
OPS = [{"wid": "agenda", "action": "add_meeting", "payload": {"title": "Catch up with Ethan", "startTime": "16:00"}},
       {"wid": "agenda", "action": "move_meeting", "payload": {"item": "Catch up with Ethan", "newTime": "16:30"}}]


def test_the_pass_56_telegram_gets_the_agendas_time():
    text = "Hey Ethan, quick update — our catch-up tomorrow is now at 5:00 PM. See you then!"
    new, why = mt.align(text, OPS, [MEETING])
    assert new == "Hey Ethan, quick update — our catch-up tomorrow is now at 4:30 PM. See you then!"
    assert "Catch up with Ethan" in why and "16:30" in why


def test_a_range_is_rewritten_with_start_and_end_and_a_right_time_is_left_alone():
    text = "Hey Ethan — booked us 45 minutes tomorrow afternoon, Wednesday 30 Sep, 4:00–4:45 PM, to catch up."
    new, _ = mt.align(text, OPS, [MEETING])
    assert "4:30–5:15 PM" in new and "4:00" not in new
    right = "Hey Ethan — see you tomorrow at 4:30 PM for our catch-up."
    assert mt.align(right, OPS, [MEETING]) == (right, "")


def test_twenty_four_hour_and_spanish_keep_their_style():
    es = "Hola Ethan, la reunión de mañana (ponernos al día) es a las 17:00."
    new, _ = mt.align(es, OPS, [MEETING])
    assert new.endswith("es a las 16:30.")


def test_no_meeting_in_the_window_or_no_shared_word_means_no_touch():
    text = "Hey Ethan, dinner is at 8:00 PM on Friday."
    assert mt.align(text, [], [MEETING]) == (text, "")
    assert mt.align("The dentist moved to 5:00 PM.", OPS, [MEETING]) == ("The dentist moved to 5:00 PM.", "")
    assert mt.align("Hey Ethan, see you tomorrow afternoon!", OPS, [MEETING]) == ("Hey Ethan, see you tomorrow afternoon!", "")


def test_the_brains_door_aligns_a_send_before_it_leaves(monkeypatch):
    """`widgets.dispatch_tag` is the provider's door (every FAST data-op of the model passes here) and
    `widget_data_turn` the probe's; both ask `meeting_time.align_payload` before the send runs."""
    import widgets
    from widgets import server_api
    sent = {}

    async def _fake_brain_action(wid, action, payload):
        sent.update({"wid": wid, "action": action, "payload": payload}); return {"ok": True}
    monkeypatch.setattr(server_api, "brain_action", _fake_brain_action)
    monkeypatch.setattr(mt, "_recent_ops", lambda: OPS)
    monkeypatch.setattr(mt, "_meetings", lambda: [MEETING])
    asyncio.run(widgets.dispatch_tag("data", {"id": "mensajeria", "data": {"action": "send_to", "payload": {
        "contact": "Ethan", "platform": "telegram", "text": "Hey Ethan, our catch-up tomorrow is now at 5:00 PM."}}}))
    assert sent["payload"]["text"].endswith("now at 4:30 PM.")
    probe = (ENGINE / "nucleo/flash/widget_data_turn.py").read_text("utf-8")
    assert "meeting_time as _mt" in probe and "_mt.align_payload(" in probe, "the text channel takes the same door"
