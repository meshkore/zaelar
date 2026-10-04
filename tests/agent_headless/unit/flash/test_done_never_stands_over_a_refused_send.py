"""«Done.» never stands over a turn whose every op was refused with a reason nobody says (demo pass 104, 2026-10-04).

C5 «send ethan a telegram with the new time»: `send_to` was refused («no tengo el Telegram de Ethan» — an internal
`error`, addressed to the model, so `report_failure` only leaves it as a note for the NEXT turn) and, the model
having said nothing, the canned success ack spoke «Done.» ten milliseconds later. The operator was told a message
went out that never did. The ack now waits for this turn's ops; when all of them were refused unsaid, the reason
is said instead.
"""
from __future__ import annotations

import asyncio


def _run(results, delay=0.0):
    from nucleo.flash import data_ops

    async def go():
        async def op(r):
            await asyncio.sleep(delay)
            return r
        tasks = [("mensajeria", asyncio.ensure_future(op(r))) for r in results]
        return await data_ops.refused_unsaid(tasks, timeout=1.0)
    return asyncio.run(go())


def test_an_internal_refusal_is_returned_to_be_said():
    why = _run([{"ok": False, "error": "no tengo el Telegram de Ethan"}], delay=0.2)
    assert why and "Telegram" in why[1], why


def test_a_success_keeps_the_ack():
    assert not _run([{"ok": True}])
    assert not _run([{"ok": True}, {"ok": False, "error": "x"}]), "one op landed — the ack is not a lie"


def test_a_refusal_the_widget_already_speaks_is_not_said_twice():
    assert not _run([{"ok": False, "error": "x", "message": "There are no more videos."}])


def test_an_op_still_running_past_the_wait_keeps_todays_path():
    assert not _run([{"ok": False, "error": "x"}], delay=2.0)


def test_the_turn_says_the_reason_and_is_no_longer_done(monkeypatch):
    from nucleo.flash import data_ops
    from nucleo.workers import spoken_delivery
    async def _line(goal, summary, ok=True, **_k):
        return "I couldn't send it — I don't have Ethan's Telegram."
    monkeypatch.setattr(spoken_delivery, "line", _line)
    sent, done = [], {"v": True}

    class _Sp:
        @staticmethod
        def sanitize(t, drop_metadata=False): return t

    async def go():
        async def op():
            return {"ok": False, "error": "no tengo el Telegram de Ethan"}
        return await data_ops.say_refusal_instead([("mensajeria", asyncio.ensure_future(op()))], done, sent.append, _Sp)
    said = asyncio.run(go())
    assert said and sent == [said] and done["v"] is False


def test_the_post_stream_asks_before_the_ack():
    import inspect
    from nucleo.flash import post_stream
    src = inspect.getsource(post_stream.run)
    assert src.index("say_refusal_instead") < src.index("settle_what_is_pending"), \
        "the canned ack (in settle) must come after the refusal check"
