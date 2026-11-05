"""C12 — negative: after a mixed turn's reply line, nothing else speaks except a task's `ask`, a worker's `say` bound to
its task, or a keyed notice (V2-851 §2c, §9)."""
from __future__ import annotations

import time

import pytest

from .probe import FINAL_STATES, brief, line_source
from .script import LANGS, MIXED, visible_rows_since

ALLOWED = ("ask", "say", "notice")


@pytest.mark.parametrize("lang", LANGS)
def test_c12_after_the_reply_only_bound_mouths_speak(probe_for, check, lang, rep):
    p = probe_for(lang)
    turn = p.say(MIXED[lang])
    reply = p.reply_line(turn)
    stray, deadline = [], time.time() + 300
    while time.time() < deadline and reply:
        stray = [e for e in p.events_since(int(reply["id"])) if line_source(e) not in ("",) + ALLOWED]
        rows = visible_rows_since(p, turn.t0)
        if stray or (rows and all(r.get("state") in FINAL_STATES for r in rows)):
            break
        time.sleep(5)
    check.that("nothing else speaks after the reply line", bool(reply) and not stray,
               [f"{line_source(e)}: {brief(e)}" for e in stray] or "no reply line")
    check.that("the turn started a task", bool(visible_rows_since(p, turn.t0)), "no row")
    check.done(expected_red=check.expected)
