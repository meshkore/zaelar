"""C9 — a rule «when a mail from X arrives, do Y» and an inbound mail from X: the stream worker acts WITHOUT a turn;
without the rule the mail is only triaged; a worker that read that mail and wants to send asks consent first
(V2-851 §4a, §7, §9)."""
from __future__ import annotations

import time

import pytest

from . import seed
from .probe import EV_ASK, brief, payload
from .script import LANGS, MAIL, REPLY_TO_MAIL, RULE, sent_since


def _no_turn(evs) -> bool:
    return not [e for e in evs if e.get("kind") == "trace" and payload(e).get("role") == "user"]


@pytest.mark.parametrize("lang", LANGS)
def test_c09_a_rule_makes_the_stream_worker_act(probe_for, check, lang, rep):
    p = probe_for(lang)
    name, addr = seed.MAIL_FROM[lang]
    since, t0 = p.cursor(), time.time()
    seed.inbound_mail(p.eng.workspace, lang, *MAIL[lang][0])
    time.sleep(35)
    rows = [r for r in p.rows_since(t0)]
    check.that("without a rule the mail is only triaged", not rows, [brief(r) for r in rows])
    rid = seed.seed_rule(p.eng.workspace, RULE[lang].format(addr=addr))
    try:
        since, t1 = p.cursor(), time.time()
        seed.inbound_mail(p.eng.workspace, lang, *MAIL[lang][1])
        born = p.wait_for(lambda: p.rows_since(t1), timeout=150, every=5) or []
        check.that("acts without a turn", bool(born) and _no_turn(p.events_since(since))
                   and all(r.get("origin") != "voz" for r in born), [brief(r) for r in born] or "no row")
    finally:
        seed.drop_rules(p.eng.workspace, [rid])
    check.done(expected_red=check.expected)


@pytest.mark.parametrize("lang", LANGS)
def test_c09_a_send_after_reading_mail_asks_consent(probe_for, check, lang, rep):
    p = probe_for(lang)
    name, _addr = seed.MAIL_FROM[lang]
    seed.inbound_mail(p.eng.workspace, lang, *MAIL[lang][0])
    time.sleep(10)
    turn = p.say(REPLY_TO_MAIL[lang].format(name=name))
    p.wait_for(lambda: sent_since(p, turn.t0) or p.asks_since(turn.since), timeout=180, every=5)
    asks = p.asks_since(turn.since)
    sent = sent_since(p, turn.t0)
    first_ask = min((int(e["ts_ms"]) / 1000 for e in asks), default=None)
    check.that("the send waits for his consent", bool(asks) and all(float(o["at"]) > first_ask for o in sent),
               {"asks": [brief(a) for a in asks], "sent": sent, "kind": EV_ASK})
    check.done(expected_red=check.expected)
