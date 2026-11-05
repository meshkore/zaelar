"""C1 — «send a message to Raquel» with two Raquels: the row waits for his answer, the question is on screen with an
id to answer it by, and the turn says ONE line (V2-851 §9)."""
from __future__ import annotations

import pytest

from .probe import EV_ASK, WAITING_USER, brief, payload
from .script import LANGS, WHO, ask_ambiguous, sent_since, visible_rows_since


@pytest.mark.parametrize("who", WHO)
@pytest.mark.parametrize("lang", LANGS)
def test_c01_an_ambiguous_name_is_a_question_on_screen(fresh_for, check, lang, who, rep):
    p = fresh_for(lang)
    turn, asks = ask_ambiguous(p, lang, who)
    ask = payload(asks[0]) if asks else {}
    check.that("the question on screen", bool(asks) and bool(ask.get("task_id")) and bool(ask.get("ask_id")),
               [brief(a) for a in asks] or f"no `{EV_ASK}` event after {turn.trace}")
    lines = [s for s, _ in p.lines_since(turn.since) if s != "ask"]
    check.that("one line for the turn", len(lines) == 1, lines)
    check.that("nothing left the machine", not sent_since(p, turn.t0), sent_since(p, turn.t0))
    rows = visible_rows_since(p, turn.t0)
    row = next((r for r in rows if r.get("id") == ask.get("task_id")), rows[0] if rows else {})
    check.that("the row waits for his answer",
               row.get("state") == "waiting" and row.get("waiting_for") == WAITING_USER, brief(row) or "no row")
    check.that("the question is durable on the row",
               bool(row.get("ask")) and row.get("ask_id") == ask.get("ask_id"), brief(row))
    check.that("the row carries its session", bool(row.get("session_id")), brief(row))
    check.done(expected_red=check.expected)
