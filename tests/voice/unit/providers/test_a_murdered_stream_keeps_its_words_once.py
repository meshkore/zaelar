"""fix10 · a stream murdered mid-sentence keeps the operator's words exactly once.

Measured live, session 6d19df41: 14 turns streamed and were then murdered by the
next fragment (13 of them pre-token, cut 462-3031 ms) plus 3 pre-stream drops.
The operator dictates in 1-4 s bursts while TTFT runs 1-3 s, so no dispatch-time
rule can tell a doomed turn from a surviving one — every fragment looks complete
standalone («It is car.», «No.», «Why didn't you get this in the first place?»).
Per-trace reconciliation of that session: 38 prompts = 23 replies + 14 murders
with exactly one scissors line each + 3 pre-stream drops, also one line each.
No stream vanished without an outcome, and no murdered words were lost: the
successors re-merged them (7 «frase completada en varios tiempos»).

What makes that churn survivable is a three-step choreography in the voice
provider, pinned here so it cannot come loose:

1. the stream's CancelledError handler preserves the OPERATOR text
   (`push_user`, prefix-coalesced so STT growth never duplicates);
2. the same handler sets `_death_logged`, so the `_run` wrapper stays silent;
3. the wrapper still re-runs its own preserve step on the re-raise, and the
   coalesce keeps it a single entry rather than a duplicate.

Break any one step and murders either lose words (the T6 ferry disaster: the
next turn answers without the criteria) or flood the log with double scissors.
"""
from __future__ import annotations

import pytest

from nucleo.flash import dialog as _dialog

# Verbatim victims from session 6d19df41: turn i=838 streamed «It is car.» and
# died pre-token (cut 1195 ms); its successor merged the spelling tail.
_MURDERED = "It is car."
_SUCCESSOR = "It is car. W o w in the message list"


class _StreamMurdered:
    """The state a turn is in when LiveKit murders its stream: the handler has
    run (preserved + flagged + reported) and the CancelledError re-raise is now
    travelling up to the `_run` wrapper. Binds the REAL wrapper function."""

    def __init__(self, window, flagged=True):
        from voice.engine.llm.providers import nucleo
        self._llm = type("B", (), {"_window": window})()
        self._chat_ctx = object()
        self._phase = "streaming"
        self._death_logged = flagged  # the stream handler sets this, line ~2038
        self._note_death = nucleo.NucleoLLMStream._note_death.__get__(self)


def test_the_wrapper_adds_nothing_when_the_stream_already_reported(monkeypatch):
    """One murder = one scissors line. The stream's handler preserved the words
    and reported with metrics; on the re-raise the wrapper returns early — no
    second line, and the preserved entry is left untouched (no re-push)."""
    from voice.engine.llm.providers import nucleo
    import voice.observer as observer

    events = []
    monkeypatch.setattr(nucleo, "_last_user_text", lambda _ctx: _MURDERED)
    monkeypatch.setattr(observer, "emit",
                        lambda kind, label, **kw: events.append(label))

    window = [{"role": "user", "content": _MURDERED}]  # the stream's own push
    _StreamMurdered(window, flagged=True)._note_death("barge-in")
    assert events == []
    assert window == [{"role": "user", "content": _MURDERED}]


def test_the_wrapper_backstop_is_idempotent_first_reports_then_silent(monkeypatch):
    """Deaths the stream handler never sees (pre-stream drops, other phases)
    are preserved + reported by the wrapper itself — and running it twice still
    leaves exactly one entry and one line. The docstring promises idempotence;
    this pins it."""
    from voice.engine.llm.providers import nucleo
    import voice.observer as observer

    events = []
    monkeypatch.setattr(nucleo, "_last_user_text", lambda _ctx: _MURDERED)
    monkeypatch.setattr(observer, "emit",
                        lambda kind, label, **kw: events.append((label, kw)))

    s = _StreamMurdered([], flagged=False)
    s._note_death("pre-stream")
    s._note_death("pre-stream")  # e.g. a second except touching the same turn
    assert [m["content"] for m in s._llm._window] == [_MURDERED]
    assert len(events) == 1
    label, kw = events[0]
    assert label == "✂️ turno descartado — sin respuesta"
    assert kw["extra"]["reason"] == "pre-stream"
    assert kw["extra"]["text_kept"] is True


def test_the_successor_merge_replaces_instead_of_duplicating():
    """The session pattern: murdered v1 preserved, successor v1+v2 arrives and
    must REPLACE the tail entry, not stack a second copy of the same words."""
    window: list = []
    _dialog.push_user(window, _MURDERED)
    _dialog.push_user(window, _SUCCESSOR)
    assert window == [{"role": "user", "content": _SUCCESSOR}]

    # and a shorter re-emission afterwards adds nothing new either
    _dialog.push_user(window, _MURDERED)
    assert window == [{"role": "user", "content": _SUCCESSOR}]


def test_the_stream_handler_preserves_flags_and_reports_in_that_order():
    """Glue pin: the CancelledError handler must preserve FIRST (or the words
    are lost with the raise), then flag (or the wrapper double-reports), then
    report. If someone reorders or drops a step, the test above cannot see it
    (it binds the wrapper, not the handler), so the shape is pinned here."""
    import inspect
    from voice.engine.llm.providers.nucleo import NucleoLLMStream
    src = inspect.getsource(NucleoLLMStream._run_inner)
    # Anchor on the barge-in re-raise and walk BACK to its handler: a forward
    # search for "except asyncio.CancelledError:" lands on an inner pump-task
    # handler instead.
    end = src.index("raise  # barge-in")
    block = src[src.rindex("except asyncio.CancelledError:", 0, end):end]
    i_push = block.index("_dialog.push_user(brain._window, text)")
    i_flag = block.index("self._death_logged = True")
    i_emit = block.index("turno cancelado (barge-in/overlap)")
    assert i_push < i_flag < i_emit, "preserve, then flag, then report — in that order"
    assert "partial_chars" in block and "cut_after_ms" in block
