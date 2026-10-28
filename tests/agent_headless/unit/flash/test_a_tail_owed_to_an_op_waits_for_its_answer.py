"""A spoken line the turn OWES to a data-op («Done.», «I've gone ahead, as you asked») waits for the op's answer, and
is never said over a refusal (node 2.747).

Audit V2-783 P0-2 (2026-10-16): on the voice channel the completion tail (`after_the_completion`) and the repair tail
(`after_the_repair`) were sent the instant `_apply_widget_data` was DISPATCHED — the widget's answer arrived later, and
a refused op («no such video», «no encuentro esa cita») was followed by «Done.» and corrected afterwards
(`report_20261015-112130`: three «Done. I couldn't…» in a row). The tails are now lines the turn owes to its ops
(`data_done["owed"]`): `post_stream` says them once the ops answered, drops them when any op was refused (the
refusal is told by `report_failure`), and keeps silent while an op is still running past the wait — the card is the
answer then, never a claim.
"""
from __future__ import annotations

import asyncio
import inspect

from nucleo.flash import data_ops


class _Sp:
    @staticmethod
    def sanitize(t, drop_metadata=False):
        return t


def _run(results, owed, delay=0.0, timeout=1.0):
    sent = []

    async def go():
        async def op(r):
            await asyncio.sleep(delay)
            return r
        tasks = [("agenda", asyncio.ensure_future(op(r))) for r in results]
        done = {"v": True, "owed": list(owed)}
        said = await data_ops.say_owed_after_ops(tasks, done, sent.append, _Sp, timeout=timeout)
        return said, done
    said, done = asyncio.run(go())
    return said, sent, done


def test_a_tail_is_said_once_the_op_answered():
    said, sent, done = _run([{"ok": True}], ["Done."], delay=0.2)
    assert said == ["Done."] and sent == [" Done."] and done["owed"] == []


def test_a_tail_is_never_said_over_a_refused_op():
    said, sent, _ = _run([{"ok": False, "message": "There's no such appointment."}], ["Done."], delay=0.1)
    assert said == [] and sent == []
    said, sent, _ = _run([{"ok": True}, {"ok": False, "error": "no row"}], ["I've gone ahead, as you asked."])
    assert said == [] and sent == [], "one refusal among the turn's ops is enough: the tail would be a claim"


def test_an_op_still_running_past_the_wait_leaves_the_card_as_the_answer():
    said, sent, _ = _run([{"ok": True}], ["Done."], delay=2.0, timeout=0.2)
    assert said == [] and sent == []


def test_no_op_at_all_says_nothing():
    said, sent, _ = _run([], ["Done."])
    assert said == [] and sent == []


def test_the_voice_tails_are_owed_not_sent():
    """The two tail sites in `post_stream_acts` hand the line to `data_done["owed"]`; `post_stream` settles the owed
    lines after the refusal check and before the canned ack."""
    from nucleo.flash import post_stream, post_stream_acts
    words = inspect.getsource(post_stream_acts.complete_the_acts)
    assert "send(\" \" + speech.sanitize(_c_tail" not in words and "send(\" \" + speech.sanitize(_ar_tail" not in words
    assert words.count('data_done.setdefault("owed", []).append(') >= 2
    run = inspect.getsource(post_stream.run)
    assert run.index("say_refusal_instead") < run.index("say_owed_after_ops") < run.index("settle_what_is_pending")
