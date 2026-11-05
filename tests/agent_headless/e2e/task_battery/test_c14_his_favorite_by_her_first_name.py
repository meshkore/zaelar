"""C14 — «send a message to <his favorite's first name>» on a directory shaped like his (V2-854, the closing check).

The sandbox holds the synthetic directory of the contacts test set: nine people carry the word «Raquel» and the one he
means is his favorite saved as «Rakel» (WhatsApp, a `@lid` chat); in English five «Catherine»s and his favorite
«Katherine» (Telegram). The case reads mechanism only:

  (1) no question — no `ask` event, no row waiting on him;
  (2) the message left ONCE, to the favorite's own chat, and to nobody else (the loopback account's orders);
  (3) the row settles once, by `settle`, `done`, and its end state is attested met.

Opt-in like the whole battery (`ZAELAR_TEST_LIVE_BATTERY=1`); a sandbox of the case's own, never his engine.
"""
from __future__ import annotations

import pytest

from .contacts_seed import directory_engine  # noqa: F401 — the case's own sandbox
from .probe import EV_ASK, WAITING_USER, WRITER_SETTLE, brief, payload
from .script import visible_rows_since, wait_sent

SAY = {"es": "Mándale un mensaje a Raquel diciéndole que llego a las ocho",
       "en": "Text Catherine that I'll be there at eight"}
#: Who the sentence means (the favorite) and the chat her message must reach.
FAVORITE = {"es": ("fav-rakel", "whatsapp"), "en": ("fav-katherine", "telegram")}


@pytest.mark.parametrize("lang", ["es", "en"])
def test_c14_his_favorite_by_her_first_name(directory_engine, check, lang, rep):  # noqa: F811
    p, rows = directory_engine(lang)
    cid, platform = FAVORITE[lang]
    chat = next(ch["chatId"] for ch in rows[cid]["channels"] if ch["platform"] == platform)
    turn = p.say(SAY[lang])
    sent = wait_sent(p, turn.t0)
    p.settle_quiet(turn.since, quiet_s=10, timeout=60)
    evs = p.events_since(turn.since)

    asks = [e for e in evs if str(e.get("kind") or "") == EV_ASK]
    trows = visible_rows_since(p, turn.t0)
    waited = [r for r in trows if r.get("waiting_for") == WAITING_USER]
    check.that("no question", not asks and not waited,
               {"asks": [brief(e) for e in asks][:3], "waiting": [brief(r) for r in waited][:3]})

    mine = [o for o in sent if str(o.get("platform")) == platform and str(o.get("chatId") or o.get("to")) == chat]
    others = [o for o in sent if o not in mine]
    check.that("one message to her own chat and to nobody else", len(mine) == 1 and not others,
               {"to_her": len(mine), "others": [(o.get("platform"), o.get("chatId") or o.get("to"), o.get("name"))
                                                 for o in others][:5]})

    row = next((r for r in trows if r.get("state") in ("done", "failed", "cancelled")), trows[-1] if trows else {})
    endings = p.task_states_since(turn.since, str(row.get("id") or ""))
    check.that("settled once by settle with done", len(endings) == 1 and payload(endings[0]).get("writer")
               == WRITER_SETTLE and payload(endings[0]).get("state") == "done",
               {"row": brief(row), "endings": [payload(e) for e in endings]})
    met = [e for e in evs if str(e.get("kind") or "") == "verdict" and payload(e).get("verdict") == "met"
           and str(payload(e).get("task_id") or row.get("id")) == str(row.get("id"))]
    check.that("its end state is attested met", bool(met), [brief(e) for e in evs
                                                            if str(e.get("kind") or "") == "verdict"][:5])
    check.done(expected_red=check.expected)
