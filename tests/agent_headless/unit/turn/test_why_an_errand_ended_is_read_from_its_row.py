"""«Why did it end» is read from the row, never recalled (V2-852 T05, invariant I4).

Measured in session c8a307fd: the car search was cancelled by «yes, close task 2»; eight minutes later he asked what
had happened and the record line the prompt carries read «… · CANCELADA · hace 8 min» — no cause — so the model made
one up («I closed it when you said "No"», another utterance). Now the stop door writes the cause on the record (his
words of the turn that stopped it, `stop.stopped_by_his_turn` inside `cancel_soon`), the row's `outcome` keeps it when
it settles, and `ledger.recent` — the one reader — hands it to the prompt's record line. Variants: a flat search in
Spanish, and an outcome already written (his pick) that a stop never overwrites.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from nucleo.circuit import ledger


@pytest.fixture
def stopped(monkeypatch):
    from nucleo import dispatch
    from nucleo.turn import brief as _tb
    recs: dict = {}

    def run(goal: str, said: str, *, summary: str = ""):
        rec = SimpleNamespace(task_id=str(len(recs) + 40), title=goal[:40], goal=goal, kind="research", sheet="",
                              surface="", started=0, status="running", result_summary=summary, error_class="",
                              verdict="", waiting_on="", settled="")
        recs[rec.task_id] = rec
        rec.uid = ledger.task_uid(rec.task_id)          # the row as `ledger.opened` writes it, without its end-state ask
        ledger.store().task_put({"id": rec.uid, "title": rec.title, "goal": goal, "kind": "research", "mode": "now",
                                 "state": "running", "visible": True, "origin": "voz", "surface": "", "sheet": "",
                                 "trace_id": "", "parent_id": "", "created_at": 0, "started_at": 0})
        monkeypatch.setattr(dispatch, "resolve_sessions", lambda q: [rec.task_id])
        monkeypatch.setattr(dispatch, "get_record", lambda t: recs.get(t))
        monkeypatch.setattr(dispatch, "_LOOP", None)
        monkeypatch.setattr(_tb, "of_this_turn", lambda: {"judged": said})
        monkeypatch.setattr(dispatch, "has_active", lambda: True)
        brief = {"event": __import__("threading").Event(), "turn_id": "t", "open_ids": [],
                 "result": {_tb.REQUEST_KEY: {"choice": "order", "confidence": 0.9}, "stop_errand": {"choice": "stop", "confidence": 0.9}}}
        brief["event"].set()
        from nucleo.request import stop as sd
        assert sd.repair(brief, said, escalating=False) == [rec.task_id]   # the stop backstop
        rec.status = "cancelled"                 # the worker's cancellation lands
        ledger.closed(rec)
        return rec
    return run


@pytest.mark.parametrize("goal,said", [("Find a used Mercedes GLC 2021-22 under 30k", "yes, close task 2"),
                                       ("Busca un piso de alquiler en Lisboa", "vale, cierra eso")])
def test_a_stopped_row_carries_the_words_that_stopped_it(stopped, goal, said):
    rec = stopped(goal, said)
    row = ledger.get(rec.uid)
    assert row["state"] == "cancelled" and said in str(row.get("outcome") or ""), row
    from nucleo.turn.prompt import live_history
    line = " ".join(live_history.recent_lines())
    assert said in line, f"the record line the prompt reads lost the cause: {line!r}"


def test_an_outcome_already_written_is_kept(stopped):
    rec = stopped("Book a table in Seville", "stop it", summary="Kept your pick: Casa Robles at 21:00")
    assert ledger.get(rec.uid)["outcome"].startswith("Kept your pick")
