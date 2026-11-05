"""C6 — a door refuses (nobody to write to, or a channel she does not have): ONE line from the mouth and no model
re-run after the stream (V2-851 §2c, §8)."""
from __future__ import annotations

import pytest

from .probe import brief, is_model_run, line_source, payload
from .script import LANGS, REFUSED, person, sent_since


@pytest.mark.parametrize("variant", ["no_channel", "wrong_channel"])
@pytest.mark.parametrize("lang", LANGS)
def test_c06_a_refusal_is_one_line_and_no_rerun(probe_for, check, lang, variant, rep):
    p = probe_for(lang)
    turn = p.say(REFUSED[lang][variant].format(unreachable=person(lang, "unreachable"), single=person(lang, "single")))
    p.settle_quiet(turn.since, quiet_s=12, timeout=45)
    check.that("nothing left the machine", not sent_since(p, turn.t0), sent_since(p, turn.t0))
    lines = [s for s, _ in p.lines_since(turn.since)]
    check.that("one line", len(lines) == 1, lines)
    evs = p.events_since(turn.since)
    reply = next((e for e in evs if line_source(e) == "reply" and payload(e).get("trace") == turn.trace), None)
    after = [e for e in evs if reply and int(e["id"]) > int(reply["id"]) and is_model_run(e)
             and payload(e).get("trace") in ("", None, turn.trace)]
    check.that("no model runs after the reply line", bool(reply) and not after, [brief(e) for e in after] or "no reply")
    check.done(expected_red=check.expected)
