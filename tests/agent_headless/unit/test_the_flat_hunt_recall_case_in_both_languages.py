"""`flat-hunt-recall-the-report`, ES and US, on the harness's OWN seed, through the text probe (2026-10-14).

The live case was 1/5 in both languages over a healthy chain: two finished flat hunts seeded with their report on
the task and no sheet on disk. What it measured, turn by turn, was the probe — so this replays the same seed
(`tests/use_cases/e2e/agent/errand_seed.errands_for`, not a copy of it) through the same decision:

  1. «Enséñame lo del piso que te dije» fits both → the reply ASKS, naming both;
  2. «El de Gràcia…» names one → its report comes back on a sheet, kept AND discarded rows, and is shown —
     even when the model's `reopen_task` query is only «piso».
"""
import asyncio

import pytest

from i18n import langs
from memory import db as memdb
from memory import tasks_store as ts
from nucleo.flash import probe_decide as PD
from nucleo.flash import router_guards as RG
from tests.use_cases.e2e.agent import errand_seed
from widgets import store
from widgets.results import data as sheetdata

TURNS = {
    "es": ("Enséñame lo del piso que te dije.", "piso", "El de Gràcia, el que te pedí hace unos días."),
    "us": ("Show me the apartment thing I told you about.", "apartment", "The Williamsburg one, from a few days ago."),
}


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


@pytest.fixture
def own_sheets(tmp_path, monkeypatch):
    d = tmp_path / "wdata"
    d.mkdir()
    monkeypatch.setattr(store, "DATA_DIR", str(d))
    assert "widgets/_data" not in store.DATA_DIR, "this fixture is not isolating anything"
    return d


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    import nucleo.jev as jev
    import voice.observer as obs
    monkeypatch.setattr(jev, "enabled", lambda: False)
    monkeypatch.setattr(obs, "emit", lambda *a, **k: None)


class _Sess:
    window: list = []
    last_action = ""
    executes = True


def _turn(text: str, query: str) -> dict:
    calls = [{"name": "reopen_task", "args": {"query": query}}]
    return asyncio.run(PD.name_the_action(_hard=None, _router=RG, _tbrief=None, _vault_gate=None, ingest=None,
                                          names={"reopen_task"}, sess=_Sess(), tags=[], text=text, tool_calls=calls))


@pytest.mark.parametrize("locale", ["es", "us"])
def test_the_case_asks_naming_both_then_brings_back_the_one_he_names(fresh_db, own_sheets, monkeypatch, locale):
    monkeypatch.setattr(langs, "current_language", lambda: langs.spec("es" if locale == "es" else "en"))
    errands = errand_seed.errands_for("flat-hunt-recall-the-report", locale)
    for e in errands:
        ts.task_put(e["row"])
        for slot, payload in e["artifacts"].items():
            ts.artifact_put(e["row"]["id"], slot, payload)
    wanted, other = errands[0]["row"], errands[1]["row"]
    opening, query, naming = TURNS[locale]

    first = _turn(opening, query)
    assert first["action"] == "clarify"
    assert wanted["title"] in first.get("spoken", "") and other["title"] in first.get("spoken", ""), first

    second = _turn(naming, query)
    assert second["action"] == f"canvas:show:results::{wanted['id']}", second
    back = sheetdata.view_data(wanted["id"])
    kept = errands[0]["artifacts"]["result"]["items"]
    assert [i["title"] for i in back["items"]] == [i["title"] for i in kept]
    assert len(back["rejected"]) == len(errands[0]["artifacts"]["considered"]["rows"])
    assert all(r.get("why") for r in back["rejected"]), "a discarded flat came back without its reason"
