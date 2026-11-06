
"""V2-697 — an appointment somebody ELSE asked for waits for the operator, instead of being dropped.

Before this, `book.book()` answered «el mandato no incluye agendar» and returned: the other person had
agreed, the engine held the slot, and nobody was told. Refusing to WRITE to his calendar is right; refusing
to ASK is what these cases exist to keep fixed.

The operator's own scoping, and the reason nothing here auto-accepts: a cluster peer's handle is
SELF-DECLARED, so the name on a proposal is a label he reads and never a credential.
«De momento podemos dejar que el sistema siempre necesite aceptaciones manuales.»
"""
import pytest

from nucleo.errands import book, proposals


class _Ledger:
    """A stand-in for the durable errand ledger: the rows, and nothing else."""

    def __init__(self, rows):
        self.rows = {r["id"]: dict(r) for r in rows}
        self.closed = []

    def live(self, now=None):
        return [dict(r) for r in self.rows.values() if r["id"] not in self.closed]

    def get(self, eid):
        r = self.rows.get(eid)
        return dict(r) if r else None

    def update(self, eid, **fields):
        r = self.rows.get(eid)
        if not r:
            return None
        r.update(fields)
        return dict(r)

    def close(self, eid, outcome="closed", why=""):
        self.closed.append(eid)
        self.rows[eid]["outcome"] = outcome
        return dict(self.rows[eid])


_ERRAND = {"id": "e1", "objective": "una intro de producto", "title": "Intro northwind",
           "mandate": {"may": ["message"]}, "state": "contacting", "done_when": {}}

_DECISION = {"agreed": {"start": "2026-09-16 15:00", "end": "2026-09-16 15:30", "medium": "videollamada"}}


@pytest.fixture
def ledger(monkeypatch):
    lg = _Ledger([_ERRAND])
    monkeypatch.setattr(proposals, "_errands", lambda: lg)
    notes = []
    monkeypatch.setattr(proposals, "_tell_operator", lambda e, p: notes.append((e, p)))
    lg.notes = notes
    return lg


def test_an_agreement_we_may_not_book_is_PARKED_instead_of_dropped(ledger):
    res = book.book(dict(_ERRAND), _DECISION, party="Laura Vidal")
    assert res["ok"] is False                      # nothing was written to the calendar, which is correct
    assert res["parked"] is True                   # …and the agreement was NOT lost, which is the fix
    row = ledger.get("e1")
    assert row["state"] == proposals.STATE
    p = row["done_when"]["proposal"]
    assert p["date"] == "2026-09-16" and p["startTime"] == "15:00" and p["endTime"] == "15:30"
    assert p["party"] == "Laura Vidal"


def test_a_parked_proposal_is_offered_to_the_operator_with_who_when_and_what_for(ledger):
    book.book(dict(_ERRAND), _DECISION, party="Laura Vidal")
    rows = proposals.pending()
    assert len(rows) == 1
    assert rows[0]["party"] == "Laura Vidal"
    assert rows[0]["objective"] == "una intro de producto"
    assert rows[0]["errand_id"] == "e1"


def test_HIS_YES_is_the_grant_that_was_missing_and_the_meeting_is_written(ledger, monkeypatch):
    book.book(dict(_ERRAND), _DECISION, party="Laura Vidal")
    booked = {}

    def _fake_book(errand, decision, party=""):
        booked["errand"] = errand
        booked["decision"] = decision
        booked["party"] = party
        return {"ok": True, "date": "2026-09-16", "time": "15:00"}

    monkeypatch.setattr(book, "book", _fake_book)
    res = proposals.accept("e1")
    assert res["ok"] and res["date"] == "2026-09-16"
    # The yes IS the permission: booking runs through the ONE function that has always written a calendar row.
    assert "schedule" in booked["errand"]["mandate"]["may"]
    assert booked["decision"]["agreed"]["start"] == "2026-09-16 15:00"
    assert booked["decision"]["agreed"]["end"] == "2026-09-16 15:30"
    assert booked["party"] == "Laura Vidal"
    assert "proposal" not in ledger.get("e1")["done_when"]   # it stops being a question once he answers


def test_a_NO_closes_the_errand_and_writes_nothing(ledger, monkeypatch):
    book.book(dict(_ERRAND), _DECISION, party="Laura Vidal")
    monkeypatch.setattr(book, "book", lambda *a, **k: pytest.fail("a declined proposal must book NOTHING"))
    res = proposals.decline("e1")
    assert res["ok"] and res["party"] == "Laura Vidal"
    assert "e1" in ledger.closed
    assert proposals.pending() == []


def test_a_proposal_that_was_already_answered_cannot_be_answered_again(ledger, monkeypatch):
    book.book(dict(_ERRAND), _DECISION, party="Laura Vidal")
    proposals.decline("e1")
    assert proposals.accept("e1")["ok"] is False


def test_an_agreement_with_no_hour_is_not_a_proposal(ledger):
    res = book.book(dict(_ERRAND), {"agreed": {"medium": "videollamada"}}, party="Laura Vidal")
    assert res["ok"] is False and not res.get("parked")
    assert proposals.pending() == []
