"""«Make it fullscreen» means the card his last turn acted on — not one that arrived meanwhile (demo pass 2026-09-28).

V3: he had just asked for video number 2; while it loaded, the monitor errand's sheet popped up in the background,
and «it» went to the sheet. A2 the other way round: the only thing his turn produced was the errand's sheet, and
«Minimise that» has to reach it.
"""
from nucleo import canvas_focus as cf
from nucleo.actionmap import executor


def _turn(*touches):
    cf.note("transcript", "text-injected", role="user")
    for label, cid, src in touches:
        cf.note("widget", label, extra={"id": cid, "src": src})


def _run(monkeypatch, open_ids, phrase="Make it fullscreen."):
    from server import voice_api
    from memory import api as memapi
    monkeypatch.setattr(voice_api, "open_instances", lambda: open_ids)
    monkeypatch.setattr(memapi, "state", lambda: {"maximized_widget": ""})
    monkeypatch.setattr(memapi, "kv_get", lambda k: {"items": []} if k == "canvas_layout" else None)
    seen = []
    cf.note("transcript", "text-injected", role="user")          # the turn being answered now
    ok = executor.execute({"do": "fullscreen", "widget": "*"},
                          lambda kind, label, **k: seen.append((label, (k.get("extra") or {}).get("id"))),
                          phrase=phrase)
    return ok, seen


def test_a_sheet_that_arrived_meanwhile_does_not_steal_it(monkeypatch):
    cf._reset()
    _turn(("data:play_result", "youtube", "flash"), ("show", "results::cdc30b-2", "worker:cdc30b-2"),
          ("show", "results", "user"))
    ok, seen = _run(monkeypatch, ["youtube", "results::cdc30b-2"])
    assert ok and seen == [("fullscreen", "youtube")], seen


def test_the_errand_he_just_commissioned_is_that(monkeypatch):
    cf._reset()
    _turn(("show", "results::ab19a4-1", "worker:ab19a4-1"))
    ok, seen = _run(monkeypatch, ["agenda", "results::ab19a4-1"], phrase="Minimise that while you work.")
    assert ok and seen[-1][1] == "results::ab19a4-1", seen


def test_his_own_tab_echoing_the_canvas_never_counts(monkeypatch):
    cf._reset()
    _turn(("show", "agenda", "user"), ("close", "agenda", "user"))
    assert cf.last_turn_card(["agenda", "youtube"]) == ""
