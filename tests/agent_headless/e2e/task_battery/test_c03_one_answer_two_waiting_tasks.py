"""C3 — two tasks waiting at once and one answer: bound to the task it answers by the turn's verdict; an answer that
fits both asks WHICH among them, never the oldest (V2-851 §3a, §9)."""
from __future__ import annotations

import pytest

from .probe import ASK_AMONG, brief, payload
from .script import (AMBIGUOUS_ANSWER, LANGS, PICK, SEND_OTHER, ask_ambiguous, candidates, chat_of, sent_since,
                     visible_rows_since, wait_sent, waiting_rows)


def _two_waiting(p, lang):
    a, _ = ask_ambiguous(p, lang, "ambiguous")
    b, _ = ask_ambiguous(p, lang, "ambiguous2", template=SEND_OTHER)
    rows = waiting_rows(visible_rows_since(p, a.t0))
    return a, rows


@pytest.mark.parametrize("lang", LANGS)
def test_c03_one_answer_goes_to_the_task_it_answers(fresh_for, check, lang, rep):
    p = fresh_for(lang)
    a, rows = _two_waiting(p, lang)
    ans = p.say(PICK[lang].format(full=candidates(lang, "ambiguous")[0]["name"]))
    sent = wait_sent(p, ans.t0, chat_of(candidates(lang, "ambiguous")[0]))
    to_pablo = [o for o in sent_since(p, a.t0) if o.get("chatId") in {chat_of(c) for c in candidates(lang, "ambiguous2")}]
    still = waiting_rows(visible_rows_since(p, a.t0))
    check.that("the right task", bool(sent) and not to_pablo and len(rows) == 2 and len(still) == 1,
               {"sent": len(sent), "to_other": to_pablo, "waiting_before": [brief(r) for r in rows],
                "waiting_after": [brief(r) for r in still]})
    check.that("two tasks waited with their own question",
               len(rows) == 2 and len({r.get("ask_id") for r in rows if r.get("ask_id")}) == 2, [brief(r) for r in rows])
    check.done(expected_red=check.expected)


@pytest.mark.parametrize("lang", LANGS)
def test_c03_an_ambiguous_answer_asks_which_task(fresh_for, check, lang, rep):
    p = fresh_for(lang)
    a, rows = _two_waiting(p, lang)
    ans = p.say(AMBIGUOUS_ANSWER[lang])
    asks = p.wait_for(lambda: p.asks_since(ans.since), timeout=30, every=3) or []
    ids = {r["id"] for r in rows}
    which = [x for x in asks if ids and ids <= set(payload(x).get(ASK_AMONG) or [])]
    check.that("an ambiguous answer asks which task", bool(which), [brief(x) for x in asks] or "no ask")
    check.that("never the oldest", not sent_since(p, ans.t0) and len(waiting_rows(visible_rows_since(p, a.t0))) == 2,
               {"sent": sent_since(p, ans.t0)})
    check.done(expected_red=check.expected)
