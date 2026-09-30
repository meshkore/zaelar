#
# test_a_question_is_ranked_by_the_name_it_carries.py — demo pass 35 (2026-09-29), E1.
#
# «Is there any email from Inworld (inworld.ai) in the inbox? What is it about and when did it arrive?» ranked four
# long Telegram posts first: BM25 over the OR of every word adds the filler up, and a busy channel holds plenty
# of it. The answer said «nothing from Inworld» with the receipt in the archive. The word that names a sender is
# found by the sender column and by being uncommon here — no list of filler words, in any language.
#
import pytest

from connectors.messaging import archive

_FILLER = ("Good morning everyone, what is there to say about the market when it did what it did, and any trader "
           "from any desk knows the inbox of the week is about when to arrive and when to leave. ")
_WORDS = ["there", "any", "email", "from", "inworld", "the", "inbox", "what", "about", "and", "when", "did", "arrive"]


@pytest.fixture(autouse=True)
def isolated_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(archive, "_db_path", lambda: str(tmp_path / "archive.db"))
    archive.reset()
    for i in range(12):
        archive.record("telegram", "-100", [{"id": f"t{i}", "body": _FILLER * 3, "ts": 1000 + i}],
                       direction="in", chat_name="The Trading Room")
    for i in range(20):
        archive.record("email", f"shop{i}@x.invalid", [{"id": f"m{i}", "body": f"Your order {i} from the shop",
                                                          "ts": 2000 + i, "from": f"Shop {i}"}], direction="in")
    archive.record("email", "invoice@inworld.ai", [{"id": "inw", "ts": 3000, "from": "Inworld AI",
                                                    "body": "[Asunto: Your receipt from Inworld AI #2281-4878] $25.00"}],
                   direction="in", chat_name="Inworld AI")
    yield
    archive.reset()


def test_the_sender_it_names_comes_first():
    rows = archive.ranked(_WORDS, limit=8)
    assert rows and rows[0]["msg_id"] == "inw", [r["body"][:40] for r in rows]


def test_a_common_word_that_is_also_in_a_chat_name_is_not_a_name():
    assert "the" not in archive._naming_terms(archive._conn(), _WORDS)


def test_a_question_that_names_nobody_still_ranks_everything():
    rows = archive.ranked(["order", "shop"], limit=3)
    assert len(rows) == 3


def test_a_sender_mentioned_in_many_forwards_is_still_a_name(tmp_path, monkeypatch):
    """Demo pass 46 (2026-09-29), E1: «inworld» had grown to 21 messages — every earlier forward of the receipt
    mentions it — past the question's median word, and stopped being read as a sender, so the receipt was never
    brought to the card. A word in under 2% of the whole archive is not filler whatever the question around it."""
    monkeypatch.setattr(archive, "_db_path", lambda: str(tmp_path / "big.db"))
    archive.reset()
    for i in range(1000):
        archive.record("telegram", "-1", [{"id": f"x{i}", "body": f"market chatter number {i}", "ts": i}], direction="in")
    for i in range(12):
        archive.record("email", "ago@x.invalid", [{"id": f"fw{i}", "ts": 2000 + i,
                       "body": "Hi Quinn, forwarding the Inworld invoice"}], direction="out")
    # the question's other words, each in a handful of messages (as in the real archive: 3-10) — so the median
    # word sits below the 13 messages that mention Inworld
    for w, n in (("yes", 8), ("give", 8), ("sender", 4), ("subject", 10), ("date", 7), ("short", 3)):
        for i in range(n):
            archive.record("email", f"{w}@x.invalid", [{"id": f"{w}{i}", "ts": 4000 + i, "body": f"a note with {w}"}],
                           direction="in")
    archive.record("email", "invoice@inworld.ai", [{"id": "orig", "ts": 3000, "from": "Inworld AI",
                   "body": "Your receipt"}], direction="in", chat_name="Inworld AI")
    words = ["has", "any", "email", "arrived", "from", "inworld", "yes", "give", "sender", "subject", "date", "short"]
    assert "inworld" in archive._naming_terms(archive._conn(), words)
    archive.reset()
