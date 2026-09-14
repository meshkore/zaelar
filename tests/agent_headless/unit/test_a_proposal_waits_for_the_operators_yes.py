"""V2-697 — an appointment somebody ELSE asked for waits for the operator, instead of being dropped.

Before this, `book.book()` answered «el mandato no incluye agendar» and returned: the other person had
agreed, the engine held the slot, and nobody was told. Refusing to WRITE to his calendar is right; refusing
to ASK is what these cases exist to keep fixed.

The operator's own scoping, and the reason nothing here auto-accepts: a cluster peer's handle is
SELF-DECLARED, so the name on a proposal is a label he reads and never a credential.
«De momento podemos dejar que el sistema siempre necesite aceptaciones manuales.»
"""
import pytest

from nucleo.errands import book, proposals, verify


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


_ERRAND = {"id": "e1", "objective": "una intro de blockchain", "title": "Intro zerohash",
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
    res = book.book(dict(_ERRAND), _DECISION, party="Gavin Hayes")
    assert res["ok"] is False                      # nothing was written to the calendar, which is correct
    assert res["parked"] is True                   # …and the agreement was NOT lost, which is the fix
    row = ledger.get("e1")
    assert row["state"] == proposals.STATE
    p = row["done_when"]["proposal"]
    assert p["date"] == "2026-09-16" and p["startTime"] == "15:00" and p["endTime"] == "15:30"
    assert p["party"] == "Gavin Hayes"


def test_the_operator_is_TOLD_and_the_notice_says_it_is_not_in_the_calendar(monkeypatch):
    lg = _Ledger([_ERRAND])
    monkeypatch.setattr(proposals, "_errands", lambda: lg)
    pushed = []
    monkeypatch.setattr("voice.brain_notes.push", lambda text, key="": pushed.append((text, key)))
    book.book(dict(_ERRAND), _DECISION, party="Gavin Hayes")
    assert pushed, "a parked proposal that nobody is told about is a dropped one with extra steps"
    text, key = pushed[0]
    assert "Gavin Hayes" in text and "2026-09-16 15:00" in text
    assert "no está en el calendario" in text      # the claim that must never be made by omission
    assert key == "proposal:e1"


def test_a_parked_proposal_is_offered_to_the_operator_with_who_when_and_what_for(ledger):
    book.book(dict(_ERRAND), _DECISION, party="Gavin Hayes")
    rows = proposals.pending()
    assert len(rows) == 1
    assert rows[0]["party"] == "Gavin Hayes"
    assert rows[0]["objective"] == "una intro de blockchain"
    assert rows[0]["errand_id"] == "e1"


def test_HIS_YES_is_the_grant_that_was_missing_and_the_meeting_is_written(ledger, monkeypatch):
    book.book(dict(_ERRAND), _DECISION, party="Gavin Hayes")
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
    assert booked["party"] == "Gavin Hayes"
    assert "proposal" not in ledger.get("e1")["done_when"]   # it stops being a question once he answers


def test_a_NO_closes_the_errand_and_writes_nothing(ledger, monkeypatch):
    book.book(dict(_ERRAND), _DECISION, party="Gavin Hayes")
    monkeypatch.setattr(book, "book", lambda *a, **k: pytest.fail("a declined proposal must book NOTHING"))
    res = proposals.decline("e1")
    assert res["ok"] and res["party"] == "Gavin Hayes"
    assert "e1" in ledger.closed
    assert proposals.pending() == []


def test_a_proposal_that_was_already_answered_cannot_be_answered_again(ledger, monkeypatch):
    book.book(dict(_ERRAND), _DECISION, party="Gavin Hayes")
    proposals.decline("e1")
    assert proposals.accept("e1")["ok"] is False


def test_a_proposal_waiting_for_the_operator_is_NEVER_verified_as_done(monkeypatch):
    """Closing it would RELEASE the conversation, so the person who asked would never hear back — the
    V2-692h shape one field over."""
    monkeypatch.setattr(verify, "_agenda_rows", lambda: [
        {"date": "2026-09-16", "startTime": "15:00", "title": "algo que ya tenía"}])
    errand = dict(_ERRAND, done_when={"at": "2026-09-16 15:00",
                                      "proposal": {"date": "2026-09-16", "startTime": "15:00"}})
    assert verify.meeting_exists(errand) is False


def test_an_agreement_with_no_hour_is_not_a_proposal(ledger):
    res = book.book(dict(_ERRAND), {"agreed": {"medium": "videollamada"}}, party="Gavin Hayes")
    assert res["ok"] is False and not res.get("parked")
    assert proposals.pending() == []


def test_an_errand_that_MAY_schedule_still_books_directly(monkeypatch):
    """The parking path must not have swallowed the normal one: an errand the operator already granted
    `schedule` to never asks him again."""
    lg = _Ledger([_ERRAND])
    monkeypatch.setattr(proposals, "_errands", lambda: lg)
    monkeypatch.setattr(proposals, "park",
                        lambda *a, **k: pytest.fail("a mandated errand must never park"))
    errand = dict(_ERRAND, mandate={"may": ["message", "schedule"]})
    assert book.may_schedule(errand) is True
