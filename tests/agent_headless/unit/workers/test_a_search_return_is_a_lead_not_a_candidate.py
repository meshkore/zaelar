#
# test_a_search_return_is_a_lead_not_a_candidate.py — V2-510, and demo pass 30 (2026-09-28).
#
# V2-376 taught the SHEET path that «what comes back from a search is a LEAD, NOT a candidate». V2-510 taught
# the note path the same. Measured on `cheapest-monitor__us` round 20260830-125532: the brain offered
# «The 6 Best Budget And Cheap Monitors of 2026 - RTINGS.com» — an article headline — while eight real
# monitors waited in the sheet.
#
# Demo pass 30 moved the finding OFF the note: a one-shot note rides the next turn whatever it is about, and
# «alright close the pictures» came back with news of the monitor errand. The lead now lives on its errand and
# the background-task block shows it next to that task, still labelled for what it is.
#
import pytest

from nucleo import dispatch
from nucleo.flash import task_block
from nucleo.workers import findings


@pytest.fixture(autouse=True)
def _clean():
    findings._HANDED.clear()
    findings._LEADS.clear()
    yield
    findings._HANDED.clear()
    findings._LEADS.clear()


_HEADLINE = "The 6 Best Budget And Cheap Monitors of 2026 - RTINGS.com — a roundup of picks — https://rtings.com/x"


def _block(monkeypatch) -> str:
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [
        {"id": "1", "request": "monitor barato", "phase": "buscando", "secs": 40}])
    return " ".join(task_block.pending_task_lines())


def test_a_search_return_is_not_pushed_into_the_next_turn(monkeypatch):
    pushed: list = []
    import voice.brain_notes as bn
    monkeypatch.setattr(bn, "push", lambda text, **k: pushed.append(text))
    assert findings.hand_web_finding("1", _HEADLINE, "monitor barato") is True
    assert pushed == [], "a web lead rode the next turn as a note — the demo-pass-30 bleed"


def test_the_lead_sits_next_to_its_task_labelled_as_a_lead(monkeypatch):
    findings.hand_web_finding("1", _HEADLINE, "monitor barato")
    block = _block(monkeypatch)
    assert "ÚLTIMA PISTA DE LA WEB" in block and "RTINGS.com" in block
    assert "NO un candidato" in block


def test_a_real_answer_can_still_be_given(monkeypatch):
    """V2-236's direction: clean data was dying inside dead workers. The label leaves the door open to give
    it when it already names the thing and its price."""
    findings.hand_web_finding("1", _HEADLINE, "monitor barato")
    assert "nombre y su precio" in _block(monkeypatch)


def test_the_finding_itself_still_travels_verbatim():
    findings.hand_web_finding("1", _HEADLINE, "monitor barato")
    assert _HEADLINE in findings.last_lead("1")


def test_the_same_return_is_not_a_second_finding():
    assert findings.hand_web_finding("1", _HEADLINE, "monitor barato") is True
    assert findings.hand_web_finding("1", _HEADLINE, "monitor barato") is False


def test_the_lead_goes_with_its_session():
    findings.hand_web_finding("1", _HEADLINE, "monitor barato")
    findings.forget("1")
    assert findings.last_lead("1") == ""


def test_the_sheet_path_still_marks_the_origin_too():
    import inspect
    src = inspect.getsource(findings.hand_search_rows)
    assert '"Origen"' in src and "búsqueda web" in src
