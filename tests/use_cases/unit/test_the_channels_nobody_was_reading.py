"""Two channels the report could not see, found by auditing the whole event store.

On 2026-08-21 the harness was reading 490 of 1291 events of a round — only the channels it had already
built a column for, so it could only find defects of a shape somebody had already imagined. The two that
mattered in the failing round: five of eight workers had died, and the web search had returned exactly what
the operator asked for and never left the worker.
"""
from __future__ import annotations

import json
import sqlite3

from tests.use_cases.e2e.agent import judge as J
from tests.use_cases.e2e.agent import verify


def _db(tmp_path, rows):
    p = tmp_path / "s.db"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE events (ts_ms INTEGER, topic TEXT, kind TEXT, label TEXT, payload TEXT)")
    for i, (topic, kind, label, payload) in enumerate(rows):
        con.execute("INSERT INTO events VALUES (?,?,?,?,?)", (1000 + i, topic, kind, label, payload))
    con.commit()
    con.close()
    return str(p)


def test_a_worker_that_died_is_counted(tmp_path):
    db = _db(tmp_path, [("worker.spawned", None, None, "{}"), ("worker.spawned", None, None, "{}"),
                        ("worker.done", None, None, '{"id":"1","ok":false,"status":"error"}'),
                        ("worker.done", None, None, '{"id":"2","ok":true}')])
    got = verify.worker_health(db)
    assert got["spawned"] == 2 and got["ok"] == 1 and got["errored"] == 1


def test_the_harness_shutting_down_is_NOT_the_product_failing(tmp_path):
    """The correction that kept a phantom off the fixing agent's desk: of five workers reported dead on
    2026-08-21, two were `cancelled` with `reason: shutdown` — the round tearing the sandbox down with the
    worker still legitimately working. Counting those as defects invents three failures out of five."""
    db = _db(tmp_path, [("worker.spawned", None, None, "{}"), ("worker.spawned", None, None, "{}"),
                        ("worker.done", None, None, '{"id":"1","ok":false,"status":"error"}'),
                        ("worker.done", None, None, '{"id":"2","ok":false,"status":"cancelled"}'),
                        ("worker.cancelled", None, None, '{"id":"2","reason":"shutdown"}')])
    got = verify.worker_health(db)
    assert got["errored"] == 1, "only one actually broke"
    assert got["cancelled"] == 1 and got["cancelled_by_shutdown"] == 1


def test_the_judge_calls_honesty_about_a_dead_worker_honesty():
    txt = J.mechanism_facts({"worker_health": {"spawned": 8, "ok": 3, "errored": 3, "cancelled": 2}})
    assert "MURIERON" in txt and "DECÍA LA VERDAD" in txt
    assert "no lo puntúes" in txt, "the cancelled ones must be excused explicitly"


def test_and_says_nothing_when_every_worker_lived():
    """Sensitivity: the warning must not fire on a healthy round."""
    txt = J.mechanism_facts({"worker_health": {"spawned": 2, "ok": 2, "errored": 0, "cancelled": 0}})
    assert "MURIERON" not in txt


def test_nor_when_the_only_casualties_were_the_shutdown():
    """A round whose workers were merely cut short at the end has nothing to report as a product defect."""
    txt = J.mechanism_facts({"worker_health": {"spawned": 3, "ok": 1, "errored": 0, "cancelled": 2}})
    assert "MURIERON" not in txt


def test_a_search_answer_that_never_left_the_worker(tmp_path):
    ans = json.dumps({"text": "Estos son los monitores: 1. Philips 27E1N1800A/00 — 159,00 €"})
    db = _db(tmp_path, [("observer", "search", "🔎 resultados web", '{"text":"monitores 4k"}'),
                        ("observer", "search", "🌐 web ↩", ans)])
    got = verify.search_returns(db)
    assert got["queries"] == 1 and got["returns"] == 1
    assert got["notes_from_search"] == 0, "there is no push path from this channel"
    assert got["model_tokens_seen"] == 0, "and no token of it turned up anywhere"


def test_a_sighting_is_not_a_delivery(tmp_path):
    """The distinction that cost a wrong claim: «27US500-W» DID turn up in a note — carried there by the
    browser's Amazon URL, not by the search answer. Counting that as delivery would report the channel as
    working while it has no push path at all."""
    ans = json.dumps({"text": "1. LG 27US500-W — 169,00 €"})
    note = json.dumps({"text": "[SISTEMA] El navegador ha SACADO esto: 169 — 00 € — /LG-27US500-W/dp/X"})
    db = _db(tmp_path, [("observer", "search", "🌐 web ↩", ans),
                        ("observer", "brain", "📩 system note", note)])
    got = verify.search_returns(db)
    assert got["model_tokens_seen"] == 1, "the token is there — that is a sighting"
    assert got["notes_from_search"] == 0, "but not one note came from the search channel"


def test_the_judge_blames_delivery_not_the_turn():
    txt = J.mechanism_facts({"search_returns": {"queries": 7, "returns": 5, "model_tokens_seen": 3,
                                                "notes_from_search": 0, "sample": ["Philips 27E1N1800A/00"]}})
    assert "no es que se los callara: no los tuvo" in txt


def test_and_stays_quiet_when_the_channel_IS_delivered():
    txt = J.mechanism_facts({"search_returns": {"queries": 2, "returns": 2, "model_tokens_seen": 2,
                                                "notes_from_search": 2, "sample": ["x"]}})
    assert "LA BÚSQUEDA WEB CONTESTÓ" not in txt
