"""The engine's own «Done.» after silent actions is not the model repeating itself.

Measured 2026-09-27 (demo pass v7): two silent orders in a row («Schedule it as…», «Move it 30 minutes later»)
each left the window ack «Done.» (`record_silent_action`). The loop detector read «Done.», «Done.» as the model
looping and injected «PROHIBIDO repetir … admite el límite … o pregunta algo distinto». The next turn, «Message
Ethan on Telegram and tell him the new meeting time», came back as a needless question and no send; the same
nudge sat on W2 («Highlight the second one» → «I've highlighted Mount Baldy», no call).
"""
from nucleo.flash import dialog


def _w(*pairs):
    out = []
    for u, a in pairs:
        out.append({"role": "user", "content": u})
        if a is not None:
            out.append({"role": "assistant", "content": a})
    return out


def test_two_silent_acks_do_not_fire_the_nudge():
    w = _w(("Find me a free slot", "Tomorrow afternoon is clear after four."),
           ("Schedule it as Catch up with Ethan", None), ("Move it 30 minutes later", None))
    dialog.record_silent_action(w[:3], "Done.")          # the lane writes it after each silent act
    w = _w(("Find me a free slot", "Tomorrow afternoon is clear after four."),
           ("Schedule it as Catch up with Ethan", "Done."), ("Move it 30 minutes later", "Done."),
           ("Message Ethan on Telegram", None))
    assert dialog.loop_nudge(w) == ""


def test_the_spanish_acks_are_ours_too():
    w = _w(("Pon la agenda", "Hecho."), ("Cierra la música", "Listo."), ("Y ahora el mapa", "Hecho."), ("x", None))
    assert dialog.loop_nudge(w) == ""


def test_a_real_repeated_reply_still_fires_it():
    same = "I can't find that contact in your directory, sorry about that."
    w = _w(("Message Ethan", same), ("His name is Ethan", same), ("Ethan from San Mateo", None))
    assert dialog.loop_nudge(w) != ""
