"""A card instance (`results::ab8413-ls1`) reaches its widget from the text channel too (V2-781 T528, 2026-10-10).

Camera pair ES: «¿y los disparos de esos dos?» → the model called `results::ab8413-ls1 rejected` on the open sheet;
the text channel goes straight to `server_api.brain_action`, whose trust boundary (`_safe`) stripped the colons into
`resultsab8413-ls1` — no such widget — and the turn said «No he podido: no data module». `widgets.dispatch_tag`
(the voice door) already splits `base::instance` into the base and its `q`; the in-process door does the same now.
"""
from __future__ import annotations

import asyncio


def test_the_instance_is_the_base_widget_with_its_sheet(monkeypatch):
    from widgets import server_api as S
    seen = {}

    async def _disp(wid, action, payload):
        seen.update(wid=wid, action=action, payload=payload)
        return {"ok": True}
    monkeypatch.setattr(S, "_dispatch", _disp)
    res = asyncio.run(S.brain_action("results::ab8413-ls1", "rejected", {"rejected": []}))
    assert res.get("ok") is True
    assert seen["wid"] == "results" and seen["payload"].get("q") == "ab8413-ls1", seen


def test_a_plain_id_is_unchanged(monkeypatch):
    from widgets import server_api as S
    seen = {}

    async def _disp(wid, action, payload):
        seen.update(wid=wid, payload=payload)
        return {"ok": True}
    monkeypatch.setattr(S, "_dispatch", _disp)
    asyncio.run(S.brain_action("agenda", "show_day", {"day": "hoy"}))
    assert seen == {"wid": "agenda", "payload": {"day": "hoy"}}
