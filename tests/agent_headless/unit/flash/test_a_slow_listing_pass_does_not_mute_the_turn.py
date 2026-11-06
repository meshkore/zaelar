"""A fast listing pass that outlives its budget does not leave the turn mute (demo pass 52, 2026-09-29, A1).

«can you find me like three 27 inch 4k monitors…» — the ads index took ~40 s; the turn ended with no words and no
card, and «I'm on it» plus the sheet landed in the middle of the next order. The turn now says the errand is taken
and moves on; the search finishes in its thread and writes the sheet as it always did."""
import asyncio
import time

from nucleo.acts import search_listing as lt


def _slow_run(*a, **k):
    time.sleep(0.6)
    return {"delivered": True, "n": 3, "escalated": 0, "ctx": "", "sheet": "s"}


def test_a_fast_search_keeps_the_composed_face(monkeypatch):
    monkeypatch.setattr(lt, "fast_pass", lambda *a, **k: {"delivered": True, "n": 3, "escalated": 0, "ctx": "", "sheet": "s"})
    monkeypatch.setattr(lt, "compose_face", lambda res, text: "FACE")

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def stream(self, messages, spec=None, max_tokens=None):
            yield "Three on the sheet."
    from nucleo.llm import fast_client
    monkeypatch.setattr(fast_client, "FastClient", _Client)
    _o = asyncio.run(lt.listings({"text": "find me monitors"}, {"query": "q"}))
    res, said = _o.data, _o.say
    assert not res.get("pending") and said == "Three on the sheet."
