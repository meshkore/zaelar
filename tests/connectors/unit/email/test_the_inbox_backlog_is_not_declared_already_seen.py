"""V2-606 — the email connector was connected, working, and showing him nothing. Forever.

The operator, with the widget open on «Email — Conectado. Tus mensajes llegan aquí automáticamente.» and an
empty list: *«the Gmail thing doesn't work… the messages are not shown»*. He was right, and the connector was
not broken: it authenticated, polled, and had been told to ignore his entire mailbox.

`service._loop` seeded `_seen` with `mailbox.all_uids()` — **every UID in INBOX** — under the comment «only
triage email that arrives AFTER connecting». Measured against his real mailbox: **1110 in INBOX, 1088 UNSEEN**,
all 1110 declared already-seen at connect. And `_seen` lives in memory and is cleared on stop, so every engine
restart moved that line forward again: anything that arrived while the engine was down became invisible too.

The line the seeding should draw is the one the operator already draws himself. Mail he has READ is dealt with
and does not come back. Mail he has NOT read is the thing he is asking to see.

Two limits, both deliberate and both SAID rather than hidden:

  · a triage surface is not a mailbox — 1088 items is not a list anybody reads, so only the most recent
    `BACKFILL` unread are handed over;
  · which is why the TOTAL is recorded. Hiding 1058 mails silently is the failure being replaced; the count is
    what lets the agent say «tienes 1088 sin leer» instead of «no tienes mensajes nuevos sin leer», which is
    what it actually said, over a full inbox (session `43b7bf79`).
"""
import pytest

from connectors.email import service


class _FakeMailbox:
    """An IMAP mailbox that can tell read from unread — and one that cannot, for the fail-soft path."""

    def __init__(self, read, unread, *, split_works=True):
        self._read, self._unread, self._split_works = set(read), list(unread), split_works

    def all_uids(self):
        return set(self._read) | set(self._unread)

    def inbox_split(self):
        if not self._split_works:
            return self.all_uids(), []
        return set(self._read), list(self._unread)


@pytest.fixture(autouse=True)
def _clean():
    service._seen.clear()
    service._set_unread_total(-1)
    yield
    service._seen.clear()
    service._set_unread_total(-1)


#: The REAL decision, called by `_loop`. Re-implementing it here is what made three disarms come back green:
#: a test that mirrors the code proves the mirror works, not the product.
_seed = service.seed_from_mailbox


# ── 1) the incident, at his real scale ────────────────────────────────────────────────────────────────────────

def test_the_unread_backlog_is_not_swallowed_whole():
    mb = _FakeMailbox(read=[f"r{i}" for i in range(22)], unread=[f"u{i}" for i in range(1088)])
    _seed(mb)
    reachable = [u for u in mb.inbox_split()[1] if u not in service._seen]
    assert len(reachable) == service.BACKFILL, "el buzón entero volvió a declararse ya visto"
    assert reachable == [f"u{i}" for i in range(1088 - service.BACKFILL, 1088)], "no son los más recientes"


def test_mail_he_has_already_read_never_comes_back():
    mb = _FakeMailbox(read=["r1", "r2", "r3"], unread=["u1"])
    _seed(mb)
    assert {"r1", "r2", "r3"} <= service._seen


def test_a_small_mailbox_surfaces_all_of_its_unread():
    mb = _FakeMailbox(read=["r1"], unread=["u1", "u2", "u3"])
    _seed(mb)
    assert [u for u in ("u1", "u2", "u3") if u not in service._seen] == ["u1", "u2", "u3"]


def test_the_true_unread_total_is_recorded():
    _seed(_FakeMailbox(read=["r"], unread=[f"u{i}" for i in range(1088)]))
    assert service.unread_total() == 1088


def test_an_unmeasured_total_is_not_zero():
    """-1 and 0 are DIFFERENT, and the difference is the whole point: «no lo sé» must never render as «no tienes
    ninguno» — the exact sentence said over 1088 unread mails."""
    assert service.unread_total() == -1


# ── 2) fail-soft: a connector that cannot tell read from unread keeps the OLD behaviour ───────────────────────

def test_a_mailbox_that_cannot_split_falls_back_to_the_old_seeding():
    """Never a flood: if the split fails we do NOT suddenly dump a whole mailbox into a triage widget."""
    mb = _FakeMailbox(read=["r1"], unread=["u1", "u2"], split_works=False)
    _seed(mb)
    assert service._seen == {"r1", "u1", "u2"}
    assert service.unread_total() == 0


# ── 3) what the BRAIN is told — the sentence that made it invent the explanation ──────────────────────────────

def _line(n):
    from connectors.messaging import brief
    service._set_unread_total(n)
    return brief._email_backlog()


def test_the_brain_is_told_the_real_number_and_forbidden_the_false_sentence():
    line = _line(1088)
    assert "1088" in line
    assert "no tienes mensajes sin leer" in line.lower()      # named as forbidden, per V2-221
    assert str(1088 - service.BACKFILL) in line, "no dice cuántos quedan fuera del widget"


def test_an_empty_mailbox_says_the_empty_widget_is_correct():
    assert "0" in _line(0) and "correcto" in _line(0)


def test_an_unknown_total_says_NOTHING_rather_than_guessing():
    assert _line(-1) == ""


def test_the_widget_and_the_mailbox_are_named_as_different_things():
    """The confusion this closes, in his own words: «en mi bandeja de Gmail veo un montón» against a widget that
    holds a TRIAGED list, answered with «no tienes mensajes nuevos sin leer»."""
    line = _line(1088)
    assert "buzón" in line.lower() and "triada" in line.lower().replace("í", "i")


# ── 4) the IMAP half — the SEARCHES that decide read from unread ──────────────────────────────────────────────
# The fake mailbox above never runs `inbox_split`, so a disarm of its searches came back green. It is the piece
# that turns a mailbox into the two lists everything else depends on, and it is worth its own fake.

class _FakeIMAP:
    def __init__(self, answers, fail_on=()):
        self.answers, self.fail_on, self.queries, self.logged_out = answers, set(fail_on), [], False

    def select(self, folder):
        return ("OK", [b"1"])

    def uid(self, verb, _none, query):
        self.queries.append(query)
        if query in self.fail_on:
            raise RuntimeError("boom")
        got = self.answers.get(query)
        if got is None:
            return ("NO", [None])
        return ("OK", [b" ".join(u.encode() for u in got)] if got else [b""])

    def logout(self):
        self.logged_out = True


def _mailbox_with(imap, monkeypatch):
    from connectors.email import mailbox as mbmod
    mb = mbmod.Mailbox.__new__(mbmod.Mailbox)
    monkeypatch.setattr(mb, "_imap", lambda: imap, raising=False)
    return mb


def test_inbox_split_asks_imap_for_seen_and_unseen(monkeypatch):
    im = _FakeIMAP({"SEEN": ["1", "2"], "UNSEEN": ["7", "8", "9"]})
    read, unread = _mailbox_with(im, monkeypatch).inbox_split()
    assert im.queries == ["SEEN", "UNSEEN"], f"no preguntó por leído/no leído: {im.queries}"
    assert read == {"1", "2"}
    assert unread == ["7", "8", "9"], "el orden importa: el backfill coge los MÁS RECIENTES"
    assert im.logged_out, "dejó la conexión IMAP abierta"


def test_an_inbox_with_nothing_unread_returns_no_backlog(monkeypatch):
    read, unread = _mailbox_with(_FakeIMAP({"SEEN": ["1"], "UNSEEN": []}), monkeypatch).inbox_split()
    assert read == {"1"} and unread == []


def test_a_search_that_fails_falls_back_to_the_old_whole_inbox(monkeypatch):
    """Fail-soft in the SAFE direction: a connector that cannot tell read from unread must not dump a mailbox."""
    im = _FakeIMAP({"ALL": ["1", "2", "3"]}, fail_on=("SEEN",))
    read, unread = _mailbox_with(im, monkeypatch).inbox_split()
    assert unread == [] and read == {"1", "2", "3"}


def test_a_silent_empty_answer_is_not_read_as_an_empty_mailbox(monkeypatch):
    """Both searches coming back empty means «the server told us nothing», not «you have no mail» — reading it
    the other way would seed NOTHING and re-publish the whole inbox on every restart."""
    im = _FakeIMAP({"SEEN": [], "UNSEEN": [], "ALL": ["1", "2"]})
    read, unread = _mailbox_with(im, monkeypatch).inbox_split()
    assert read == {"1", "2"} and unread == []
