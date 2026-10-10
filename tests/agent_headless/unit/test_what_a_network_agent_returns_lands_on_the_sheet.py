"""What a MeshKore agent returns lands on the errand's sheet, like a web search's rows (V2-781 T528, 2026-10-10).

Camera pair EN: at 1.5 min the worker reported «eBay bargain agent returned 10 US candidates under $400»; the sheet
stayed empty until minute 6, when the worker finally wrote it — after the conversation had ended on «still in the
first step». A web search's return already has a door to the sheet (`findings.hand_search_rows`, V2-320); the
network agent's return (`hbmesh serve`) had none. Same door now: the rows it carries are appended to the sheet.
"""
from __future__ import annotations

import json

from nucleo import mesh_cli as M


def _run(monkeypatch, data, capsys):
    sent = []
    monkeypatch.setenv("ZAELAR_TASK_ID", "7")
    from nucleo import mesh_agents, widget_cli
    monkeypatch.setattr(mesh_agents, "serve", lambda *a, **k: {"ok": True, "agent": "ebay-finder", "data": data})
    monkeypatch.setattr(widget_cli, "_act", lambda action, payload: sent.append((action, payload)) or {"ok": True})
    M.main(["serve", "used dslr under 400"])
    json.loads(capsys.readouterr().out)          # the worker still gets the agent's answer on stdout
    return sent


def test_the_agents_items_are_appended_to_the_sheet(monkeypatch, capsys):
    data = {"results": [{"title": "Nikon D3500 + 18-55mm", "price": "$342.98", "url": "https://www.ebay.com/itm/1"},
                        {"name": "Canon Rebel T7", "price": 249, "link": "https://www.ebay.com/itm/2"}]}
    sent = _run(monkeypatch, data, capsys)
    assert sent and sent[0][0] == "widget_data", sent
    p = sent[0][1]
    assert p["widget_id"] == "results" and p["action"] == "append"
    titles = [i["title"] for i in p["payload"]["items"]]
    assert titles == ["Nikon D3500 + 18-55mm", "Canon Rebel T7"]
    assert p["payload"]["items"][1]["url"] == "https://www.ebay.com/itm/2"


def test_an_answer_without_items_writes_nothing(monkeypatch, capsys):
    assert _run(monkeypatch, {"message": "no listings matched"}, capsys) == []
