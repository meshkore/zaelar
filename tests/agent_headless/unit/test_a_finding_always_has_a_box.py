"""V2-290 — the browser extracted real rows and they fell into the box that belongs to no one.

Measured in the 2026-08-24 12:03 run. `search-buy-bicycle__es`: the browser navigated 6 times, extracted 3 times
and pulled out SEVEN bikes with a price and Wallapop link —«Bicicleta Montaña Venta en Persona, 125 €», «Rock Shox
Trutativ, 70 €»…— and all seven were written to bare `results`, while `results::3fc631-1` —the errand's sheet,
opened and with its title— remained at zero. The same happened in `search-buy-camera__es`, with fourteen. And the
bare box **has belonged to no one since V2-259**, so that was invisible by construction: the operator facing a blank
card and the results in a box nobody had opened for them.

TWO cracks in sequence, and fixing only one leaves the entire failure in place:

  1. **The tab is not always named the same way.** `dispatch._prepare_web` creates the tab and stores `rec.nav_task`
     ONLY for `kind="web"`. Any other errand that opens the browser —the bicycle RESEARCH one, for example— falls
     through to the `nucleo/nav_cli.py` fallback (`ZAELAR_NAV_TASK` or, if not, `ZAELAR_TASK_ID`), so its tab is named
     after the TASK. `sheet_for_nav_task` only matched by `nav_task`, and that route did not exist. Two ways of naming
     the same thing in two different places is how the crack was born.

  2. **And that errand may not have a sheet.** It is opened when the errand is assigned only if the brain declared
     the sheet as a surface, which is correct: you do not open an empty box for someone who will not fill it. But if it
     ends up extracting rows, the premise collapses — there are findings and nowhere to put them. It opens when the
     FIRST one arrives, which is the difference between an empty box nobody asked for and one that appears with
     something inside.
"""
import pytest

from nucleo import dispatch, sheets


class _Rec:
    """The minimum that the two functions inspect on a record."""
    def __init__(self, task_id, *, nav_task="", sheet="", status="running"):
        self.task_id, self.nav_task, self.sheet, self.status = task_id, nav_task, sheet, status
        self.goal, self.kind, self.surface = "busca una bici", "research", ""


@pytest.fixture(autouse=True)
def _clean_registry(monkeypatch):
    monkeypatch.setattr(dispatch, "_SESSIONS", {})
    yield


# ── 1) pure RESOLUTION ─────────────────────────────────────────────────────────────────────────────────────
def test_a_reserved_tab_still_resolves_by_its_nav_task():
    """The existing route still takes precedence: the reserved tab is checked first."""
    recs = [_Rec("1", nav_task="t1", sheet="b-1")]
    assert sheets.sheet_for_nav_task("t1", recs) == "b-1"


def test_a_tab_named_after_its_errand_resolves_too():
    """THE MEASURED CASE: without a reserved tab, the bridge names it by the TASK id."""
    recs = [_Rec("3", sheet="b-3")]
    assert sheets.sheet_for_nav_task("3", recs) == "b-3"


def test_the_nav_task_wins_when_both_could_match():
    """A task id can coincide with the tab of ANOTHER errand; the explicit reservation is more specific
    and must win, or a finding would end up in the neighbor's sheet."""
    recs = [_Rec("9", sheet="b-suyo"), _Rec("1", nav_task="9", sheet="b-reservada")]
    assert sheets.sheet_for_nav_task("9", recs) == "b-reservada"


def test_a_tab_with_no_errand_behind_it_still_answers_nothing():
    """The operator driving the browser manually has no errand, and that is NOT a failure: it returns "" and writes
    to the usual sheet (V2-259 contract)."""
    assert sheets.sheet_for_nav_task("t9", [_Rec("1", nav_task="t1", sheet="b-1")]) == ""
    assert sheets.sheet_for_nav_task("", [_Rec("1", nav_task="t1", sheet="b-1")]) == ""


# ── 2) on-demand OPENING, which the live registry needs ─────────────────────────────────────────────────────
def _opened(monkeypatch):
    """Stamps the sheet as `_sheet_open` would, without touching the widget store.

    ⚠️ It is patched in `nucleo.sheets`, which is WHERE IT IS USED, not in `dispatch`, which only re-exports it by name:
    redirecting `dispatch`'s name leaves the real caller calling the real function. It caused a red test when the
    body of a function was moved between modules, and it is the same trap that makes extracting anything a test
    patches by its private name dangerous."""
    seen = []

    def _fake(rec):
        seen.append(rec)
        rec.sheet = f"hoja-{rec.task_id}"
    monkeypatch.setattr(sheets, "_sheet_open", _fake)
    return seen


def test_the_first_finding_opens_the_box_its_errand_never_had(monkeypatch):
    """THE FULL MEASURED CASE: live errand, no sheet, and a tab that has just extracted data."""
    seen = _opened(monkeypatch)
    dispatch._SESSIONS["3"] = _Rec("3")                    # no `sheet`: its surface was not the sheet
    assert dispatch.sheet_for_nav_task("3") == "hoja-3"
    assert len(seen) == 1


def test_an_errand_that_already_has_a_box_is_not_opened_again(monkeypatch):
    """Opening it again is the “search deletion error” that V2-259 was intended to remove."""
    seen = _opened(monkeypatch)
    dispatch._SESSIONS["3"] = _Rec("3", sheet="b-3")
    assert dispatch.sheet_for_nav_task("3") == "b-3"
    assert seen == []


def test_a_finding_from_a_dead_errand_opens_nothing(monkeypatch):
    """A finding that arrives late does not open a card on the screen of someone who has already moved on."""
    seen = _opened(monkeypatch)
    dispatch._SESSIONS["3"] = _Rec("3", status="done")
    assert dispatch.sheet_for_nav_task("3") == ""
    assert seen == []


def test_nothing_is_opened_for_a_tab_nobody_owns(monkeypatch):
    """The manually operated browser keeps writing to the usual sheet, without opening boxes along the way."""
    seen = _opened(monkeypatch)
    dispatch._SESSIONS["3"] = _Rec("3", sheet="b-3")
    assert dispatch.sheet_for_nav_task("t9") == ""
    assert seen == []
