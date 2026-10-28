from tests import voice_turn_source as _vts
"""Closing a card is a TOOL, like opening one (demo pass 2026-09-28).

Showing had `show_widget`; closing only the [[close]] text tag. Measured on the human-script turns with the
engine's own prompt and tools: «ok close the calendar» sent every model tried (deepseek flash and pro, glm-5.3)
to the nearest FUNCTION — `agenda:close_meeting`, `results:clear` (which emptied the sheet), or a show+close
pair. With `close_widget` in the catalogue, deepseek-flash called it for all three (close, close, minimize).
"""
import pytest

from nucleo.flash import router_catalog, show_target


@pytest.fixture(autouse=True)
def _no_leftover_focus():
    from nucleo import canvas_focus
    canvas_focus._reset()
    yield
    canvas_focus._reset()          # «it» is process state: never leave a turn behind for the next test file


def _tool(name):
    return next(t["function"] for t in router_catalog.TOOLS if t["function"]["name"] == name)


def test_close_is_in_the_catalogue_beside_show():
    f = _tool("close_widget")
    assert f["parameters"]["properties"]["mode"]["enum"] == ["close", "minimize"]
    assert "delete_widget" in f["description"] and "widget_data" in f["description"], \
        "it says what it is NOT — the two neighbours every model reached for"


def test_it_converges_on_the_canvas_route_of_the_tag(monkeypatch):
    tags, events = [], []
    rid = show_target.close_dispatch({"widget_id": "agenda", "mode": "close"},
                                     lambda a, x: tags.append((a, x.get("id"))), lambda *a, **k: events.append(a))
    assert rid == "agenda" and tags == [("close", "agenda")]
    tags.clear()
    show_target.close_dispatch({"widget_id": "results", "mode": "minimize"},
                               lambda a, x: tags.append((a, x.get("id"))), lambda *a, **k: None)
    assert tags == [("minimize", "results")], "«put that away while you work» sets it aside, never closes it"


def test_an_empty_id_is_the_card_his_last_turn_acted_on(monkeypatch):
    from nucleo import canvas_focus as cf
    from server import voice_api
    cf._reset()
    cf.note("transcript", "", role="user")
    cf.note("widget", "show", extra={"id": "results::ab-1", "src": "worker:ab"})
    cf.note("transcript", "", role="user")
    monkeypatch.setattr(voice_api, "open_instances", lambda: ["agenda", "results::ab-1"])
    assert show_target.close_target("") == "results::ab-1"


def test_the_voice_turn_routes_it():
    assert 'name == "close_widget"' in _vts.turn_source()


def test_a_close_is_not_acknowledged_as_an_open():
    """S4: «ok close the results» → «I've opened it, though there's nothing in it yet.» Driven through the typed
    channel, which runs the voice turn: the model closes the card and says nothing."""
    import asyncio
    from tests.brain import harness as H
    text = "ok close the results"
    case = {"id": "close", "lang": "en", "phrase": text, "source": "test", "screen": {"open": ["results"]},
            "expect": "talk", "model": {"tools": [{"name": "close_widget",
                                                   "args": {"widget_id": "results", "mode": "close"}}]}}
    with H.Isolated("en") as iso:
        iso.seed(case)
        from nucleo.cli import turn
        try:
            res = asyncio.run(turn.run_turn(text, sid="close", ingest=False))
        finally:
            turn.reset("close")
    assert res["action"].startswith("canvas:close"), res
    assert "opened" not in res["reply"].lower(), res["reply"]


def test_the_piece_named_closes_its_one_open_card(monkeypatch):
    """S4: the close went to the bare «results» and the sheet `results::c79ebf-1` stayed on screen."""
    from server import voice_api
    monkeypatch.setattr(voice_api, "open_instances", lambda: ["contactos", "results::c79ebf-1"])
    assert show_target.close_target("results") == "results::c79ebf-1"
    monkeypatch.setattr(voice_api, "open_instances", lambda: ["results::a-1", "results::b-1"])
    assert show_target.close_target("results") == "results", "two sheets: the tag's own resolution asks"


# ── demo passes 38/45/47 (2026-09-29), S4: «ok close the results» with more than one «results» open ──────────────

def test_a_bare_shell_beside_the_sheet_closes_the_sheet(monkeypatch):
    """The base card («results») counted as open beside the sheet: the close went to the bare id, the sheet stayed."""
    from server import voice_api
    monkeypatch.setattr(voice_api, "open_instances", lambda: ["results", "results::cd18f5-ls1"])
    assert show_target.close_target("results") == "results::cd18f5-ls1"


def test_two_sheets_close_the_one_his_last_turn_acted_on(monkeypatch):
    from nucleo import canvas_focus as cf
    from server import voice_api
    cf._reset()
    cf.note("transcript", "", role="user")
    cf.note("widget", "show", extra={"id": "results::b-1", "src": "flash"})
    cf.note("transcript", "", role="user")
    monkeypatch.setattr(voice_api, "open_instances", lambda: ["results::a-1", "results::b-1"])
    assert show_target.close_target("results") == "results::b-1"
    cf._reset()
    assert show_target.close_target("results") == "results", "no focus, two real sheets: still a question"
