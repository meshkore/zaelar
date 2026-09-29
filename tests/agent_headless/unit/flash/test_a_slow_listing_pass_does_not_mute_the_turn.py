"""A fast listing pass that outlives its budget does not leave the turn mute (demo pass 52, 2026-09-29, A1).

«can you find me like three 27 inch 4k monitors…» — the ads index took ~40 s; the turn ended with no words and no
card, and «I'm on it» plus the sheet landed in the middle of the next order. The turn now says the errand is taken
and moves on; the search finishes in its thread and writes the sheet as it always did."""
import asyncio
import time

from nucleo.flash import listing_turn as lt


def _slow_run(*a, **k):
    time.sleep(0.6)
    return {"delivered": True, "n": 3, "escalated": 0, "ctx": "", "sheet": "s"}


def test_the_turn_speaks_and_moves_on_while_the_search_finishes(monkeypatch):
    monkeypatch.setattr(lt, "run", _slow_run)
    monkeypatch.setattr(lt, "FAST_PASS_BUDGET_S", 0.1)
    monkeypatch.setattr(lt, "_taken_line", lambda: "I'll let you know as soon as I have it.")
    got = []

    async def _turn():
        t0 = time.monotonic()
        res, said = await lt.voice_turn({"query": "27 inch 4k monitor"}, "find me monitors", on_delta=got.append)
        return res, said, time.monotonic() - t0
    res, said, took = asyncio.run(_turn())     # asyncio.run joins the search thread on shutdown: measured inside
    assert took < 0.5, "the turn did not wait for the search"
    assert res["pending"] is True and said == "I'll let you know as soon as I have it." and got == [said]


def test_a_promise_already_spoken_is_not_repeated(monkeypatch):
    monkeypatch.setattr(lt, "run", _slow_run)
    monkeypatch.setattr(lt, "FAST_PASS_BUDGET_S", 0.1)
    monkeypatch.setattr(lt, "_taken_line", lambda: "On it.")
    res, said = asyncio.run(lt.voice_turn({"query": "q"}, "find me monitors", already_said="I'm on it — …"))
    assert res["pending"] is True and said == ""


def test_a_fast_search_keeps_the_composed_face(monkeypatch):
    monkeypatch.setattr(lt, "run", lambda *a, **k: {"delivered": True, "n": 3, "escalated": 0, "ctx": "", "sheet": "s"})
    monkeypatch.setattr(lt, "compose_face", lambda res, text: "FACE")

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def stream(self, messages, spec=None, max_tokens=None):
            yield "Three on the sheet."
    from nucleo.flash import fast_client
    monkeypatch.setattr(fast_client, "FastClient", _Client)
    res, said = asyncio.run(lt.voice_turn({"query": "q"}, "find me monitors"))
    assert not res.get("pending") and said == "Three on the sheet."
