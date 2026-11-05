"""C5 — a confirmed send: the connector's echo settles the row through `circuit.settle`, exactly ONE writer of its
final state, and ONE line (V2-851 §3b, §9)."""
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
    states = [payload(e) for e in p.task_states_since(turn.since, row.get("id", ""))]
    check.that("one writer", len(states) == 1 and states[0].get("writer") == WRITER_SETTLE
               and states[0].get("state") in FINAL_STATES, {"row": brief(row), "task_state": states})
    lines = [s for s, _ in p.lines_since(turn.since)]
    check.that("one line", len(lines) == 1, lines)
    check.done(expected_red=check.expected)
