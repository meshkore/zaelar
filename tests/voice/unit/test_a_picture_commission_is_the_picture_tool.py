"""A commission that lands on the picture viewer is the picture TOOL, never a worker (node 2.187).

Demo passes 60-62, B1 (2026-09-29): «now let's make it prettier, find me the wallpaper cosmic eye in the sky by
tyler young, the helix nebula» was escalated to a Brain Worker; passes 56-59 ran it as `show_images` in 3 s and B2
set it as the wallpaper. The late catalogue question could not name the viewer (its criterion was cut before the
word «wallpaper»; now it leads with it), and even named, the viewer's `show` needs pictures a TURN TOOL finds — so
the commission pass's «show {query}» becomes the `show_images` request instead of a data-op that returns «no
pictures arrived».
"""
import asyncio

from nucleo.flash import card_commission as cc

SAID = "now let's make it prettier, find me the wallpaper cosmic eye in the sky by tyler young, the helix nebula"


def test_a_show_with_a_query_and_no_pictures_is_the_tool_request_and_keeps_the_wallpaper_intent():
    got = cc._as_tool_request({"kind": "call", "widget_id": "imagenes", "action": "show",
                               "payload": {"query": "cosmic eye in the sky helix nebula tyler young"}}, SAID)
    assert got["query"] == "cosmic eye in the sky helix nebula tyler young wallpaper" and got["more"] is False
    assert cc._as_tool_request({"kind": "call", "widget_id": "imagenes", "action": "add",
                                "payload": {"query": "ferrari f40"}}, "more of those")["more"] is True


def test_a_real_data_op_is_left_alone(monkeypatch):
    monkeypatch.setattr(cc, "_viewer_empty", lambda: False)
    assert cc._as_tool_request({"widget_id": "imagenes", "action": "show", "payload": {"items": [{"url": "u"}]}}, SAID) is None
    assert cc._as_tool_request({"widget_id": "imagenes", "action": "wallpaper", "payload": {"item": 1}}, SAID) is None
    assert cc._as_tool_request({"widget_id": "agenda", "action": "show", "payload": {"query": "x"}}, SAID) is None
    assert cc._as_tool_request({"widget_id": "imagenes", "action": "show", "payload": {}}, SAID) is None


def test_before_worker_spends_the_tool_not_the_worker(monkeypatch):
    monkeypatch.setattr(cc, "named_or_catalogue", lambda brief, text, **k: "imagenes")
    from nucleo.flash import act_repair

    async def _pass(*a, **k):
        return {"kind": "call", "widget_id": "imagenes", "action": "show",
                "payload": {"query": "cosmic eye in the sky helix nebula"}}
    monkeypatch.setattr(act_repair, "call_or_read_for_commission", _pass)
    esc, read, images, emitted, applied = {"v": "Find the photograph…", "more": []}, {"v": None}, {"v": None}, [], []
    out = asyncio.run(cc.before_worker(esc, read, brief={"x": 1}, operator_text=SAID, spec=None,
                                       emit=lambda *a, **k: emitted.append(a), present=lambda *a, **k: True,
                                       apply_widget_data=lambda *a: applied.append(a), images_req=images))
    assert out == "call" and esc["v"] is None and applied == []
    assert images["v"]["query"].startswith("cosmic eye in the sky") and "wallpaper" in images["v"]["query"]


def test_the_viewer_criterion_names_the_wallpaper_before_the_cut():
    from nucleo.flash import turn_brief as tb
    crit = tb.catalog_question()["criteria"]["imagenes"]
    assert "wallpaper" in crit.lower() and "fondo de escritorio" in crit.lower()


def test_the_voice_turn_hands_its_image_request_to_the_rung():
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[3] / "voice/engine/llm/providers/nucleo.py").read_text(encoding="utf-8")
    assert "window=list(brain._window), images_req=images_req) == \"call\":" in src


def test_an_order_on_an_EMPTY_viewer_is_first_a_search(monkeypatch):
    """Demo pass 63, B1: the pass called `wallpaper` with nothing on the viewer, and it failed."""
    monkeypatch.setattr(cc, "_viewer_empty", lambda: True)
    got = cc._as_tool_request({"widget_id": "imagenes", "action": "wallpaper", "payload": {"item": 1}}, SAID)
    assert got and "cosmic eye in the sky" in got["query"] and got["more"] is False
    got = cc._as_tool_request({"widget_id": "imagenes", "action": "wallpaper",
                               "payload": {"item": "cosmic eye in the sky helix nebula"}}, SAID)
    assert got["query"].startswith("cosmic eye in the sky helix nebula") and "wallpaper" in got["query"]


def test_a_commission_on_an_empty_viewer_is_the_search_even_when_the_pass_calls_nothing(monkeypatch):
    """Demo pass 66, B1: the catalogue named the viewer (0.71) and the pass still sent the wallpaper to a worker."""
    monkeypatch.setattr(cc, "named_or_catalogue", lambda brief, text, **k: "imagenes")
    monkeypatch.setattr(cc, "_viewer_empty", lambda: True)
    from nucleo.flash import act_repair

    async def _nothing(*a, **k):
        return None
    monkeypatch.setattr(act_repair, "call_or_read_for_commission", _nothing)
    esc = {"v": 'Find the wallpaper artwork "Cosmic Eye in the Sky" by Tyler Young, featuring the Helix Nebula. '
                'Download the highest-resolution version available.', "more": []}
    images = {"v": None}
    out = asyncio.run(cc.before_worker(esc, {"v": None}, brief={"x": 1}, operator_text=SAID, spec=None,
                                       emit=lambda *a, **k: None, present=lambda *a, **k: True,
                                       apply_widget_data=lambda *a: None, images_req=images))
    assert out == "call" and esc["v"] is None
    assert images["v"]["query"].startswith('Find the wallpaper artwork "Cosmic Eye in the Sky"')
    assert "Download" not in images["v"]["query"]


def test_wallpaper_names_the_viewer():
    from widgets import runtime
    assert runtime.identify_named("set that as my wallpaper") == "imagenes"
    assert runtime.identify_named("ponlo de fondo de pantalla") == "imagenes"
