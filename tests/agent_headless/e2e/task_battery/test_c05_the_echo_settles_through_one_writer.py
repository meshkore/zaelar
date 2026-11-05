"""C5 — a confirmed send: the connector's echo settles the row through `circuit.settle`, exactly ONE writer of its
final state, and ONE line about the ending (V2-851 §3b, §9, §2c).

The echo of a chat send lands after the turn (the card composes it for a few seconds before it leaves), so the turn's
reply says the START and the out-of-turn mouth says the ENDING with the row's `task_id`: that pair is the design. What
must hold is that the ending is said once — by the reply only when the row had already ended before it, else by one
line naming the row — and that nothing else speaks."""
from __future__ import annotations

import pytest

from .probe import FINAL_STATES, WRITER_SETTLE, brief, payload
from .script import LANGS, SEND_SINGLE, person, visible_rows_since, wait_sent


@pytest.mark.parametrize("channel", ["telegram", "email"])
@pytest.mark.parametrize("lang", LANGS)
def test_c05_the_echo_settles_through_one_writer(probe_for, check, lang, channel, rep):
    p = probe_for(lang)
    turn = p.say(SEND_SINGLE[lang][channel].format(who=person(lang, "single")))
    sent = [o for o in wait_sent(p, turn.t0) if o.get("platform") == channel]
    check.that("the message left", bool(sent), sent or "no order reached the loopback account")
    rows = visible_rows_since(p, turn.t0)
    row = rows[-1] if rows else {}
    p.wait_for(lambda: p.task_states_since(turn.since, row.get("id", "")), timeout=30, every=3)
    p.settle_quiet(turn.since, quiet_s=10, timeout=40)
    state_evs = p.task_states_since(turn.since, row.get("id", ""))
    states = [payload(e) for e in state_evs]
    check.that("one writer", len(states) == 1 and states[0].get("writer") == WRITER_SETTLE
               and states[0].get("state") in FINAL_STATES, {"row": brief(row), "task_state": states})
    lines = p.lines_since(turn.since)
    ended_at = int(state_evs[0]["id"]) if state_evs else None
    ending = [s for s, ev in lines
              if (s == "say" and str(payload(ev).get("task_id") or "") == str(row.get("id") or ""))
              or (s == "reply" and ended_at is not None and int(ev["id"]) > ended_at)]
    check.that("one line about the ending", len(ending) == 1 and len(lines) <= 2,
               {"ending": ending, "lines": [(s, str(payload(ev).get("text") or ev.get("text") or "")[:120])
                                            for s, ev in lines]})
    check.done(expected_red=check.expected)
