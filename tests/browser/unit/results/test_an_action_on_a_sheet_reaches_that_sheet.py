"""A data-op aimed at a CARD (`results::be35a9-1:layout`) reaches the results widget with that sheet.

Measured 2026-09-27 (verification after the demo pass): once an action on a sheet stopped being escalated, the
dispatch passed `results::be35a9-1` to the trust boundary, whose `_safe` strips the colons — `resultsbe35a9-1`,
no such widget, `action_failed`. «Compare them visually» failed on the sheet it had just brought up.
"""
import asyncio

import widgets
from widgets import server_api


def test_the_instance_travels_as_q_to_the_base_widget(monkeypatch):
    seen = {}

    async def fake(wid, name, payload):
        seen.update(wid=wid, name=name, payload=payload)
        return {"ok": True}

    monkeypatch.setattr(server_api, "brain_action", fake)
    res = asyncio.run(widgets.dispatch_tag("widget.data", {"id": "results::be35a9-1",
                                                           "data": {"action": "layout", "payload": {"mode": "grid"}}}))
    assert res.get("ok") and seen == {"wid": "results", "name": "layout",
                                      "payload": {"mode": "grid", "q": "be35a9-1"}}, seen


def test_an_explicit_sheet_is_kept_and_a_base_id_is_untouched(monkeypatch):
    seen = []

    async def fake(wid, name, payload):
        seen.append((wid, payload))
        return {"ok": True}

    monkeypatch.setattr(server_api, "brain_action", fake)
    asyncio.run(widgets.dispatch_tag("widget.data", {"id": "results::a", "data": {"action": "x", "payload": {"sheet": "b"}}}))
    asyncio.run(widgets.dispatch_tag("widget.data", {"id": "agenda", "data": {"action": "show_day", "payload": {}}}))
    assert seen == [("results", {"sheet": "b"}), ("agenda", {})]
