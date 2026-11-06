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
