"""«Me los pasas cuando tengas los enlaces y años» with backed rows on the errand's sheet is answered with the rows
NOW — the model's «en cuanto los tenga, te los paso» promise never stands alone over a sheet that holds them
(node 2.661).

search-buy-boat-multicountry ES (2026-10-14, sandbox 093838-es): that turn's sheet held two listing PAGES and the
candidate (Lagoon 440 de 2009, 299.000 €, link) lived only in the search's prose — fixed at the source by node
2.662. This pins the other half on the round's own words: once the candidate IS a row, his «pásamelos cuando los
tengas» is a «tell» turn and the rows ride the reply.
"""
from __future__ import annotations

import threading

from nucleo.flash import delivery, live_blocks

ERRAND = "Búscame un catamarán Lagoon 440 de segunda mano por menos de 300.000 euros, en España, Francia o Italia."
ROWS = ["Lagoon 440 de 2009 — 299.000 € — https://www.yachtworld.es/barcos/2009-lagoon-440-123/"]
HEARD = "Vale, suena bien. Me los pasas cuando tengas los enlaces y años."
REPLY = "Vale, así lo haré: en cuanto tenga los enlaces y los años, te los paso. Ahora mismo: entrando en boat24.com."


def _brief() -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t", "open_ids": [], "_call_id": "t",
            "result": {"wants_words": {"choice": "tell", "confidence": 1.0},
                       "escalate_or_inline": {"choice": "handle_inline", "confidence": 1.0}}}


def test_his_send_them_when_you_have_them_gets_the_rows_now(monkeypatch):
    monkeypatch.setattr(live_blocks, "any_stalled_task", lambda: ("", 0, ""))
    monkeypatch.setattr(delivery, "_speaks_en", lambda: False)
    monkeypatch.setattr(live_blocks, "any_live_task_rows", lambda n=3: (ERRAND, ROWS[:n]))
    delivery.forget_announced()
    out = delivery.apply_to_reply(REPLY, [{"role": "user", "content": ERRAND}], heard_now=HEARD, brief=_brief())
    assert "Lagoon 440 de 2009" in out and "299.000 €" in out, out


def test_with_no_rows_the_promise_stands(monkeypatch):
    monkeypatch.setattr(live_blocks, "any_stalled_task", lambda: ("", 0, ""))
    monkeypatch.setattr(delivery, "_speaks_en", lambda: False)
    monkeypatch.setattr(live_blocks, "any_live_task_rows", lambda n=3: (ERRAND, []))
    delivery.forget_announced()
    out = delivery.apply_to_reply(REPLY, [], heard_now=HEARD, brief=_brief())
    assert out.startswith("Vale, así lo haré"), out
    assert "299.000" not in out
