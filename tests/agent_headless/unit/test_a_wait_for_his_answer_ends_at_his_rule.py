"""V2-851 §11.1 — «7 days, then cancel»: a task waiting for his answer ends at the period HIS rule gives, said once.

The operator's decision (2026-11-05): a task with `waiting_for=user_answer` does not expire before 7 days; at 7 days
from `waiting_since` the pulse closes it through `circuit.settle(cancelled)` with one line by the out-of-turn mouth
(«I closed X because you did not answer»), never silently. The period is a RULE with readers — a `rules` row, scope
`global`, default 7 days from genesis — not a constant: a row of his own wins, and it applies to waits already open.
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest

import rules
from memory import db as memdb
from memory import tasks_store as ts
from nucleo.circuit import ledger as T

DAY = 86400
ENGINE = Path(__file__).resolve().parents[3]


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    rules._reset_for_tests()
    yield
    rules._reset_for_tests()
    memdb.reset_db()


@pytest.fixture
def states(monkeypatch):
    from voice import observer
    seen: list[dict] = []
    real = observer.emit

    def _emit(kind, *a, **k):
        if kind == "task_state":
            seen.append(dict(k.get("extra") or {}))
            return None
        return real(kind, *a, **k)
    monkeypatch.setattr(observer, "emit", _emit)
    return seen


def _waiting(uid, days_ago, waiting_for="user_answer", ask="Which Raquel?"):
    now = int(time.time())
    ts.task_put({"id": uid, "title": "photos for Raquel", "goal": "send Raquel the photos", "state": "running",
                 "created_at": now - 30 * DAY, "started_at": now - 30 * DAY})
    T.waiting(uid, waiting_for, ask=ask, now=now - days_ago * DAY)


# ── the period is a rule ─────────────────────────────────────────────────────────────────────────────────────
def test_the_period_is_a_global_rule_whose_default_is_seven_days(fresh_db):
    genesis = json.loads((ENGINE / "nucleo/genesis.json").read_text(encoding="utf-8"))
    assert genesis["tasks"][T.ANSWER_WAIT_KEY] == 7
    row = rules.resolve([(0, rules.GLOBAL)])["rules"].get(T.ANSWER_WAIT_KEY)
    assert row and row["source"] == "default" and row["scope"] == "global" and row["value"] == 7
    assert T.answer_wait_s() == 7 * DAY


def test_his_own_row_wins_and_applies_to_the_waits_already_open(fresh_db, states):
    _waiting("ab12cd-1", days_ago=3)
    assert T.expired_waits() == []
    rules.add("global", "pref", T.ANSWER_WAIT_KEY, 2, text="give up on a question after two days")
    assert T.answer_wait_s() == 2 * DAY
    assert [r["id"] for r in T.expired_waits()] == ["ab12cd-1"]


# ── the close ────────────────────────────────────────────────────────────────────────────────────────────────
def test_only_a_wait_for_his_answer_past_its_period_is_cancelled_through_settle(fresh_db, states):
    _waiting("ab12cd-2", days_ago=8)
    _waiting("ab12cd-3", days_ago=6)
    _waiting("ab12cd-4", days_ago=30, waiting_for="send_echo", ask="")
    closed = T.expired_waits()
    assert [r["id"] for r in closed] == ["ab12cd-2"] and closed[0]["days"] == 7
    row = ts.task_get("ab12cd-2")
    assert row["state"] == "cancelled" and "Which Raquel?" in row["outcome"]
    assert [(e["task_id"], e["state"], e["writer"]) for e in states] == [("ab12cd-2", "cancelled", "settle")]
    assert ts.task_get("ab12cd-3")["state"] == "waiting" and ts.task_get("ab12cd-4")["state"] == "waiting"
    assert T.expired_waits() == [], "a closed wait is closed once"


def test_the_pulse_closes_it_and_says_one_line_keyed_to_the_task(fresh_db, states, monkeypatch):
    from nucleo import dispatch
    from nucleo.pulse import notices
    from nucleo.pulse.loop import OrchestratorLoop
    from voice.engine.core import langs
    said: list[tuple] = []

    async def _notify(title, text, *, key, kind="reminder", **k):
        said.append((text, key, kind))
        return {"id": 1, "state": "spoken", "channel": "voice", "duplicate": False}
    monkeypatch.setattr(notices, "notify", _notify)
    monkeypatch.setattr(dispatch, "sync_state", lambda: None)
    monkeypatch.setattr(dispatch, "active_sessions", lambda: [])
    monkeypatch.setattr(dispatch, "unclosed_uids", lambda: set())
    _waiting("ab12cd-5", days_ago=9)

    async def _noop(*a, **k):
        return None
    asyncio.run(OrchestratorLoop(deliver=_noop)._supervise_workers(time.time()))
    assert ts.task_get("ab12cd-5")["state"] == "cancelled"
    line = langs.current_language().task_wait_expired.format(goal="photos for Raquel", days="7")
    assert said == [(line, "task:ab12cd-5:expired", "info")]


@pytest.mark.parametrize("lang", ["es", "en"])
def test_the_line_is_in_both_languages_and_names_the_task(lang):
    pack = json.loads((ENGINE / f"i18n/genesis/{lang}/voice.json").read_text(encoding="utf-8"))
    line = pack["task_wait_expired"]
    assert "{goal}" in line and "{days}" in line
