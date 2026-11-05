"""C2 — C1 answered by screen (with its `ask_id`) or by voice: the SAME session resumes, no new row, and the message
leaves to the person he chose (V2-851 §3a, §9)."""
from __future__ import annotations

import pytest

from .probe import brief, payload
from .script import LANGS, PICK, ask_ambiguous, candidates, chat_of, visible_rows_since, wait_sent, waiting_rows


def _resumed(check, p, lang, turn, before):
    chosen, other = candidates(lang, "ambiguous")[:2]
    sent = wait_sent(p, turn.t0, chat_of(chosen))
    stray = [o for o in wait_sent(p, turn.t0, chat_of(other), timeout=1)]
    check.that("the message left to the chosen person", bool(sent) and not stray, {"sent": sent, "stray": stray})
    after = p.row(before["id"]) if before else None
    check.that("the same session resumes",
               bool(before and before.get("session_id")) and bool(after)
               and after.get("session_id") == before.get("session_id") and after.get("state") != "waiting",
               {"before": brief(before or {}), "after": brief(after or {})})
    rows = visible_rows_since(p, turn.t0)
    check.that("no new row for the answer", len(rows) == 1, [brief(r) for r in rows])


@pytest.mark.parametrize("lang", LANGS)
def test_c02_a_screen_answer_resumes_the_same_session(probe_for, check, lang, rep):
    p = probe_for(lang)
    turn, asks = ask_ambiguous(p, lang)
    ask = payload(asks[0]) if asks else {}
    before = next(iter(waiting_rows(visible_rows_since(p, turn.t0))), None)
    task_id = ask.get("task_id") or (before or {}).get("id")
    full = candidates(lang, "ambiguous")[0]["name"]
    status, body = p.answer(task_id, ask.get("ask_id", ""), full) if task_id else (0, "no question with an id")
    check.that("the screen answer is accepted", status == 200 and isinstance(body, dict) and body.get("ok"),
               f"{status} {str(body)[:200]}")
    _resumed(check, p, lang, turn, before)
    check.done(expected_red=check.expected)


@pytest.mark.parametrize("lang", LANGS)
def test_c02_a_voice_answer_resumes_the_same_session(probe_for, check, lang, rep):
    p = probe_for(lang)
    turn, _asks = ask_ambiguous(p, lang)
    before = next(iter(waiting_rows(visible_rows_since(p, turn.t0))), None)
    p.say(PICK[lang].format(full=candidates(lang, "ambiguous")[0]["name"]))
    _resumed(check, p, lang, turn, before)
    check.done(expected_red=check.expected)
