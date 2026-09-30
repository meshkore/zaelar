"""The listing pass does not repeat what the turn already said (demo pass 2026-09-28, full14 A1).

«can you find me like three 27 inch 4k monitors…» — the model said «I'll pull them onto your screen when I've got
them.», the search went to the background, and the listing pass then spoke the same promise again, glued on:
«…got them.I'm already digging deep on this, looking for three 27-inch 4K monitors…»."""
from tests import voice_turn_source as _vts
import asyncio

from nucleo.flash import listing_turn as lt


class _Client:
    calls: list = []

    def __init__(self, *a, **k):
        pass

    async def stream(self, messages, spec=None, max_tokens=None):
        _Client.calls.append(messages)
        for d in ("Three are ", "on the sheet."):
            yield d


def _rig(monkeypatch, delivered):
    from nucleo.flash import fast_client
    monkeypatch.setattr(fast_client, "FastClient", _Client)
    monkeypatch.setattr(lt, "run", lambda *a, **k: {"delivered": delivered, "n": 3 if delivered else 0,
                                                    "escalated": 0 if delivered else 1, "ctx": "", "sheet": "s"})
    monkeypatch.setattr(lt, "compose_face", lambda res, text: "FACE")
    _Client.calls = []


def test_a_search_handed_to_the_background_adds_nothing_to_a_promise_already_spoken(monkeypatch):
    _rig(monkeypatch, delivered=False)
    _, said = asyncio.run(lt.voice_turn({"query": "27 inch 4k monitor"}, "find me monitors",
                                        already_said="I'll pull them onto your screen when I've got them."))
    assert said == "" and _Client.calls == []


def test_rows_that_landed_are_told_knowing_what_was_said(monkeypatch):
    _rig(monkeypatch, delivered=True)
    _, said = asyncio.run(lt.voice_turn({"query": "27 inch 4k monitor"}, "find me monitors",
                                        already_said="On it."))
    assert said == "Three are on the sheet."
    assert "YA LE HAS DICHO" in _Client.calls[0][0]["content"] and "On it." in _Client.calls[0][0]["content"]


def test_a_silent_turn_still_gets_its_sentence(monkeypatch):
    _rig(monkeypatch, delivered=False)
    _, said = asyncio.run(lt.voice_turn({"query": "q"}, "find me monitors"))
    assert said == "Three are on the sheet." and "YA LE HAS DICHO" not in _Client.calls[0][0]["content"]


def test_the_voice_channel_hands_over_what_it_said_and_spaces_the_continuation():
    from pathlib import Path
    prov = _vts.read(Path(__file__).resolve().parents[4] / "voice/engine/llm/providers/nucleo.py")
    assert "already_said=_said_before" in prov and '" " + _d.lstrip()' in prov
