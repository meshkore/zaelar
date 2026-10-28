"""`flat-hunt-recall-the-report`, ES and US, on the harness's OWN seed, through the typed turn (2026-10-14).

The live case was 1/5 in both languages over a healthy chain: two finished flat hunts seeded with their report on
the task and no sheet on disk. This replays the same seed (`tests/use_cases/e2e/agent/errand_seed.errands_for`, not
a copy of it) through the one turn — the voice turn, typed and dry (`nucleo.cli.turn.run_turn`, refactor2710-01):

  1. «Enséñame lo del piso que te dije» fits both → the reply ASKS, naming both;
  2. «El de Gràcia…» names one → its report comes back on a sheet, kept AND discarded rows, and is shown —
     even when the model's `reopen_task` query is only «piso».
"""
import asyncio

import pytest

from tests.brain import harness as H
from tests.use_cases.e2e.agent import errand_seed

TURNS = {
    "es": ("Enséñame lo del piso que te dije.", "piso", "El de Gràcia, el que te pedí hace unos días."),
    "us": ("Show me the apartment thing I told you about.", "apartment", "The Williamsburg one, from a few days ago."),
}


@pytest.mark.parametrize("locale", ["es", "us"])
def test_the_case_asks_naming_both_then_brings_back_the_one_he_names(locale):
    from memory import tasks_store as ts
    from widgets.results import data as sheetdata
    sid = f"flat-hunt-{locale}"
    with H.Isolated("es" if locale == "es" else "en"):
        from nucleo.cli import turn
        errands = errand_seed.errands_for("flat-hunt-recall-the-report", locale)
        for e in errands:
            ts.task_put(e["row"])
            for slot, payload in e["artifacts"].items():
                ts.artifact_put(e["row"]["id"], slot, payload)
        wanted, other = errands[0]["row"], errands[1]["row"]
        opening, query, naming = TURNS[locale]

        def _turn(text: str) -> dict:
            H.RecordedModel.load({"say": "", "tools": [{"name": "reopen_task", "args": {"query": query}}]})
            return asyncio.run(turn.run_turn(text, sid=sid, ingest=False))

        try:
            first = _turn(opening)
            assert first["action"] == "clarify", first
            assert wanted["title"] in first.get("reply", "") and other["title"] in first.get("reply", ""), first

            second = _turn(naming)
            assert second["action"] == f"canvas:show:results::{wanted['id']}", second
            back = sheetdata.view_data(wanted["id"])
            kept = errands[0]["artifacts"]["result"]["items"]
            assert [i["title"] for i in back["items"]] == [i["title"] for i in kept]
            assert len(back["rejected"]) == len(errands[0]["artifacts"]["considered"]["rows"])
            assert all(r.get("why") for r in back["rejected"]), "a discarded flat came back without its reason"
        finally:
            turn.reset(sid)
