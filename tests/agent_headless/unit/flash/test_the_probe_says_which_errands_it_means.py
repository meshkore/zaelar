"""The text probe ASKS which errand, naming them, with the voice's own phrase (2026-10-14).

`flat-hunt-recall-the-report` ES and US: ten turns of `reopen_task` → `clarify`, and not one of them asked anything.
The probe named the action and carried no question, so the reply fell to the mute backstop («Perdona, se me ha
ido. ¿Me lo dices otra vez?» / «Sorry, I lost that») and he never heard that there were two flat hunts to pick from.
The voice lane says `ask_which_item` with the candidates; now the probe says the same line.
"""
import asyncio

import pytest

from i18n import langs
from memory import db as memdb
from memory import tasks_store as ts
from nucleo.flash import probe_decide as PD
from nucleo.flash import router_guards as RG


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


@pytest.fixture(autouse=True)
def no_jev(monkeypatch):
    import nucleo.jev as jev
    monkeypatch.setattr(jev, "enabled", lambda: False)


class _Sess:
    def __init__(self, executes: bool):
        self.window, self.last_action, self.executes = [], "", executes


def _turn(text: str, query: str, *, executes: bool) -> dict:
    calls = [{"name": "reopen_task", "args": {"query": query}}]
    return asyncio.run(PD.name_the_action(_hard=None, _router=RG, _tbrief=None, _vault_gate=None, ingest=None,
                                          names={"reopen_task"}, sess=_Sess(executes), tags=[], text=text,
                                          tool_calls=calls))


def _put(tid: str, title: str, at: int):
    ts.task_put({"id": tid, "title": title, "goal": title, "state": "done", "visible": True,
                 "created_at": at, "finished_at": at + 60})


@pytest.mark.parametrize("executes", [True, False])
def test_two_flat_hunts_are_a_question_that_names_both_es(fresh_db, monkeypatch, executes):
    monkeypatch.setattr(langs, "current_language", lambda: langs.spec("es"))
    _put("g", "Pisos de alquiler en Gràcia", 2000)
    _put("s", "Pisos de alquiler en Sant Antoni", 1000)
    blk = _turn("Enséñame lo del piso que te dije.", "piso", executes=executes)
    assert blk["action"] == "clarify"
    said = blk.get("spoken") or ""
    assert said.startswith("¿Cuál exactamente?"), said
    assert "Gràcia" in said and "Sant Antoni" in said, f"the question names neither errand: {said!r}"


def test_two_apartment_hunts_are_a_question_that_names_both_us(fresh_db, monkeypatch):
    monkeypatch.setattr(langs, "current_language", lambda: langs.spec("en"))
    _put("w", "Apartments for rent in Williamsburg", 2000)
    _put("a", "Apartments for rent in Astoria", 1000)
    blk = _turn("Show me the apartment thing I told you about.", "apartment", executes=True)
    assert blk["action"] == "clarify"
    said = blk.get("spoken") or ""
    assert said.startswith("Which one exactly?") and "Williamsburg" in said and "Astoria" in said, said


def test_nothing_on_file_asks_nothing_it_cannot_name(fresh_db, monkeypatch):
    """No candidates → no invented question: the model's own words stand (no `spoken` key overrides them)."""
    monkeypatch.setattr(langs, "current_language", lambda: langs.spec("es"))
    blk = _turn("lo del piso que te dije", "piso", executes=True)
    assert blk["action"] == "clarify" and "spoken" not in blk
