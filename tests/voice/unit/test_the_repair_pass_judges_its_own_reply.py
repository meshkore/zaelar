"""The second pass for a call judges its own reply: a CLAIM or a PROMISE gets its call, an answer or a proposal
does not (demo pass 2026-09-28).

E3 «draft a short reply…» → «I've got a draft ready» with no call, and the verdict too unsure (0.58) to open the
repair gate. The gate had a 0.8 floor because the old repair prompt ASSUMED a promise and booked a meeting that C2
had only proposed. Measured live with the new prompt: C2's proposal and C2's answer → no call; E3's claimed draft →
`draft`; C4's «moved it to 2 PM» → `move_meeting`; R1's plain answer → no call. Live model: ZAELAR_LIVE_JEV=1.
"""
import asyncio
import os

import pytest

from nucleo.flash import act_repair as ar

_live = pytest.mark.skipif(os.getenv("ZAELAR_LIVE_JEV") != "1", reason="live model — set ZAELAR_LIVE_JEV=1")

CASES = [
    ("agenda", "find me a free 45 minutes tomorrow afternoon to talk with rowan",
     "Tomorrow afternoon 1:30 to 2:15 is free, or anytime from 4 PM. Want me to set it up?", None),
    ("agenda", "when's the tesla insurance due again?", "Your Tesla insurance renews on 12 March 2027.", None),
    ("mensajeria", "draft a short reply saying i'll send the meet link right after our call",
     "I've got a draft ready saying you'll send the Meet link right after your call.", "draft"),
    ("agenda", "actually move it half an hour later", "Checking… moved it to 2 PM.", "move_meeting"),
    # demo pass 2026-09-28: an OFFER is not the act (C2 booked it once) — but a claimed act followed by an offer
    # of ANOTHER one still gets its call (C4: «Moved to 2:45. Want me to let Rowan know it's on?», nothing moved)
    ("agenda", "find me a free 45 minutes tomorrow afternoon to talk with rowan",
     "4:30 to 5:15 fits nicely with nothing in the way. Want me to put the call with Rowan there?", None),
    ("agenda", "actually move it half an hour later", "Moved to 2:45.\n\nWant me to let Rowan know it's on?",
     "move_meeting"),
]


@pytest.fixture
def agenda_with_the_meeting(tmp_path, monkeypatch):
    """The card as it was: the meeting a «move it» refers to is ON it (an empty agenda has nothing to move)."""
    import datetime
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.agenda import data as ag
    tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    ag.apply_action("add_meeting", {"title": "Catch up with Rowan", "date": tomorrow,
                                    "startTime": "14:15", "endTime": "15:00"})


@_live
@pytest.mark.parametrize("wid,said,reply,want", CASES)
def test_a_claim_gets_its_call_and_an_answer_does_not(agenda_with_the_meeting, wid, said, reply, want):
    import server.common  # noqa: F401 — the credential store, for the live model
    got = asyncio.run(ar.call_for_promise(said, reply, wid))
    assert (got or {}).get("action") == want, got


def test_the_prompt_asks_it_to_judge():
    assert "PROPOSED" in ar._SYS and "CLAIMED" in ar._SYS   # V2-778 F2-19: the repair prompts are English
