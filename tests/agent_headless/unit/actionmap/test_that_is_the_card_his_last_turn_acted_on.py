"""«Make it fullscreen» means the card his last turn acted on — not one that arrived meanwhile (demo pass 2026-09-28).

V3: he had just asked for video number 2; while it loaded, the monitor errand's sheet popped up in the background,
and «it» went to the sheet. A2 the other way round: the only thing his turn produced was the errand's sheet, and
«Minimise that» has to reach it.
"""
import pytest

from nucleo import canvas_focus as cf
from nucleo.actionmap import executor


@pytest.fixture(autouse=True)
def _no_leftover_focus():
    cf._reset()
    yield
    cf._reset()


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


def test_exit_fullscreen_reaches_the_full_screen_he_ordered_when_the_canvas_says_nothing(monkeypatch):
    """V4: two tabs report the canvas; the last one to speak had nothing maximised, «Exit fullscreen» found no
    target, and the model said «Done, back to normal» over a video still at full screen."""
    cf._reset()
    _turn(("fullscreen", "youtube", "actionmap"))
    from memory import api as memapi
    monkeypatch.setattr(memapi, "state", lambda: {"maximized_widget": ""})
    seen = []
    ok = executor.execute({"do": "unfullscreen"},
                          lambda kind, label, **k: seen.append((label, (k.get("extra") or {}).get("id"))),
                          phrase="Exit fullscreen.")
    assert ok and seen == [("minimize", "youtube")], seen
    cf.note("widget", "minimize", extra={"id": "youtube", "src": "actionmap"})
    assert cf.ordered_fullscreen() == "", "undone once it is taken out"


# ── demo pass 2026-09-28, U3 — «pause it a sec» paused the VIDEO while the music he had just asked for played ──

def _subject(monkeypatch, phrase, open_ids=("youtube", "musica")):
    from memory import api as memapi
    from nucleo.flash import direct_action as da
    monkeypatch.setattr(memapi, "state", lambda: {"open_widgets": list(open_ids)})
    return da.subject_card("youtube", "pause", phrase)


def test_a_show_over_the_open_card_is_a_touch_and_it_becomes_it(monkeypatch):
    # «put like a prayer» on the music card that was already up: the door refuses the show as `already_open`
    cf.note("transcript", "text-injected", role="user")
    cf.note("widget", "🚫 presentación suprimida", extra={"id": "musica", "src": "flash", "already_open": True})
    cf.note("transcript", "text-injected", role="user")                # «pause it a sec»
    assert _subject(monkeypatch, "pause it a sec") == "musica"


def test_a_card_he_names_always_wins(monkeypatch):
    cf.note("transcript", "text-injected", role="user")
    cf.note("widget", "show", extra={"id": "musica", "src": "flash"})
    cf.note("transcript", "text-injected", role="user")
    assert _subject(monkeypatch, "pause the video") == "youtube"


def test_a_suppressed_show_for_another_reason_is_no_touch():
    cf.note("transcript", "text-injected", role="user")
    cf.note("widget", "🚫 presentación suprimida", extra={"id": "musica", "src": "flash", "already_open": False})
    cf.note("transcript", "text-injected", role="user")
    assert cf.last_turn_card(["musica", "youtube"]) == ""


def test_the_door_marks_the_already_open_refusal():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[4] / "nucleo/flash/canvas_visibility.py").read_text("utf-8")
    assert 'return _suppress("ya está abierta", already_open=True)' in src
