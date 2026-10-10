"""What the agent SAYS goes in the session's language, like what it sends (V2-781).

Measured in `knows-who-i-am-without-being-told-again__us` (2026-10-10): «I'm in Madrid btw» and the English session
answered «¡Perfecto, Madrid apuntado! Te busco una receta…», and the worker's spoken notice came in Spanish too.
The door that already held outgoing messages (`outgoing_lang`, demo pass 106) now holds the reply and the notice.
"""
import asyncio
import inspect

from nucleo.flash import outgoing_lang as ol


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _session(monkeypatch, code):
    from i18n import langs
    monkeypatch.setattr(langs, "current_code", lambda: code)
    seen = []

    async def _tr(text, name):
        seen.append(text); return "Perfect, Madrid noted! I'll find you a gluten-free rice bowl recipe."
    monkeypatch.setattr(ol, "_translate", _tr)
    return seen


def test_a_spanish_reply_in_an_english_session_is_translated(monkeypatch):
    seen = _session(monkeypatch, "en")
    out = _run(ol.said_in_session_language("¡Perfecto, Madrid apuntado! Te busco una receta de bol de arroz y te la dejo en pantalla."))
    assert out.startswith("Perfect") and seen


def test_the_sync_check_tells_without_yielding(monkeypatch):
    _session(monkeypatch, "en")
    assert ol.foreign_to_session("Ya está en tu pantalla: un bol de arroz con salmón, sin gluten.")
    assert not ol.foreign_to_session("Your three dinners are ready on screen.")


def test_a_reply_already_in_the_session_language_is_left_alone(monkeypatch):
    seen = _session(monkeypatch, "en")
    assert _run(ol.said_in_session_language("Got it, I'll find you a recipe for the rice bowl.")).startswith("Got it")
    assert _run(ol.said_in_session_language("Vale.")) == "Vale."
    assert not seen


def test_both_doors_are_wired():
    from nucleo.flash import probe
    from nucleo.workers import spoken_delivery
    assert "said_in_session_language" in inspect.getsource(probe)
    assert "foreign_to_session" in inspect.getsource(spoken_delivery)
