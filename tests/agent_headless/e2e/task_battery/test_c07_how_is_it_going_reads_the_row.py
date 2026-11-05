"""C7 — «how is the Raquel thing going?» while it waits: one line composed from the row; the worker does not wake
(V2-851 §2b, §9)."""
from __future__ import annotations

import pytest

from .probe import bridge_acts, brief, payload
from .script import LANGS, STATUS, ask_ambiguous, person, visible_rows_since, waiting_rows


@pytest.mark.parametrize("lang", LANGS)
def test_c07_how_is_it_going_reads_the_row(probe_for, check, lang, rep):
    p = probe_for(lang)
    turn, _ = ask_ambiguous(p, lang)
    row = next(iter(waiting_rows(visible_rows_since(p, turn.t0))), {})
    st = p.say(STATUS[lang].format(who=person(lang, "ambiguous")))
    p.settle_quiet(st.since, quiet_s=10, timeout=40)
    lines = [s for s, _ in p.lines_since(st.since)]
    check.that("one line for the question", len(lines) == 1, lines)
    acts = bridge_acts(p.events_since(st.since), str(row.get("session") or ""), "") if row else []
    check.that("the worker does not wake", not acts, [brief(a) for a in acts])
    read = [e for e in p.flow(st.trace) if row and payload(e).get("task_id") == row.get("id")]
    check.that("the line is composed from the row", bool(row) and bool(read), brief(row) or "no waiting row")
    check.done(expected_red=check.expected)
