"""C4 — a question asked, the engine restarted: the row still waits, the question is shown again, the answer resumes
the SAME session and opens no new row (V2-851 §3, §9)."""
from __future__ import annotations

import pytest

from .probe import Probe, WAITING_USER, brief, payload, same_task_resumed
from .script import LANGS, PICK, ask_ambiguous, candidates, chat_of, visible_rows_since, wait_sent, waiting_rows


@pytest.mark.parametrize("lang", LANGS)
def test_c04_a_question_survives_a_restart(own_engine, check, lang, rep):
    p = Probe(own_engine(lang), session="bat-c04")
    turn, asks = ask_ambiguous(p, lang)
    before = next(iter(waiting_rows(visible_rows_since(p, turn.t0))), None)
    q = Probe(own_engine.restart(p.eng, lang), session="bat-c04")
    since = q.cursor()
    after = q.row(before["id"]) if before else next(iter(visible_rows_since(q, turn.t0)), None)
    check.that("still waiting", bool(after) and after.get("state") == "waiting"
               and after.get("waiting_for") == WAITING_USER, brief(after or {}) or "no row after the restart")
    again = q.wait_for(lambda: q.asks_since(since), timeout=30, every=3) or []
    old_id = payload(asks[0]).get("ask_id") if asks else None
    check.that("the question is shown again", bool(old_id) and any(payload(x).get("ask_id") == old_id for x in again),
               [brief(x) for x in again])
    ans = q.say(PICK[lang].format(full=candidates(lang, "ambiguous")[0]["name"]))
    sent = wait_sent(q, ans.t0, chat_of(candidates(lang, "ambiguous")[0]), timeout=120,
                     rows=[before["id"]] if before else ())
    end = q.row(before["id"]) if before else None
    check.that("the same task resumes", bool(sent) and same_task_resumed(before, end), brief(end or {}))
    check.that("zero new rows", len(visible_rows_since(q, turn.t0)) == 1, [brief(r) for r in visible_rows_since(q, turn.t0)])
    check.done(expected_red=check.expected)
