"""A repair pass never sends a message to a person nobody named (V2-781, build-workout-tracker-widget__es).

«Vale, avísame cuando esté» with the widget build running: the reply promised «te aviso en cuanto esté lista», the
repair asked the model for the call it «should have made» over `mensajeria`, and it produced
`send_to {"contact": "zaelar"}` — the assistant's own name. The send failed and the raw directory error reached him.
An outbound message from a repair is only legitimate for a recipient his words or the conversation carry.
"""
import asyncio

from nucleo.flash import act_repair


def _run(text, window=None, contact="zaelar"):
    from nucleo.flash import fast_client

    class _FC:
        async def complete(self, messages, *, on_tool_call=None, **kw):
            on_tool_call("widget_data", {"widget_id": "mensajeria", "action": "send_to",
                                         "payload": {"contact": contact, "text": "Te aviso en cuanto esté."}})
            return ""
    fast_client.FastClient = _FC
    return asyncio.new_event_loop().run_until_complete(
        act_repair.call_for_promise(text, "Vale, te aviso en cuanto esté lista.", "mensajeria", window=window))


def test_a_send_to_a_contact_nobody_named_is_dropped(monkeypatch):
    from nucleo.flash import fast_client
    monkeypatch.setattr(fast_client, "FastClient", fast_client.FastClient)
    assert _run("Vale, avísame cuando esté.") is None


def test_a_send_to_the_person_he_named_survives(monkeypatch):
    from nucleo.flash import fast_client
    monkeypatch.setattr(fast_client, "FastClient", fast_client.FastClient)
    got = _run("mándale a Rowan que llego tarde", contact="Rowan")
    assert got and got["action"] == "send_to"
    got = _run("díselo", window=[{"role": "user", "content": "escríbele a Rowan por Telegram"}], contact="rowan")
    assert got and got["payload"]["contact"] == "rowan"
