"""The round plays the canvas: after each turn it reports the open cards, as the desktop does (V2-781).

Measured in `tres-tarjetas-y-el-video-por-alusion` (2026-10-10): the engine learns which cards are open ONLY from
the desktop's `POST /api/canvas/state`. A sandbox has no desktop, so with the trailer, the music and the agenda on
screen the turn brief asked `catalog_widget` (the «nothing is open» question), «pause the video» read `none` and the
reply «Paused.» went out over no call. Every multi-card case was measured on a blind engine.
"""
import inspect

from tests.use_cases.e2e.agent import verify


def _w(ts, label, wid=""):
    return {"t_ms": ts, "cat": "widget", "label": label, "id": wid}


def test_shows_and_closes_fold_into_what_is_open():
    evs = [_w(1, "show", "youtube"), _w(2, "show", "musica"), _w(3, "show", "agenda"), _w(4, "close", "youtube"),
           {"t_ms": 5, "cat": "brain", "label": "show", "id": "x"}]
    assert verify.canvas_now(evs) == ["agenda", "musica"]


def test_a_close_with_no_id_clears_the_canvas():
    assert verify.canvas_now([_w(1, "show", "agenda"), _w(2, "close")]) == []


def test_instances_keep_their_card_id():
    assert verify.canvas_now([_w(1, "show", "results::ab12")]) == ["results::ab12"]


def test_the_round_posts_it():
    from tests.use_cases.e2e.agent import run
    src = inspect.getsource(run)
    assert "canvas_now(" in src and "/api/canvas/state" in src


def test_a_close_the_desktop_applies_is_folded_in():
    evs = [_w(1, "show", "youtube"), _w(2, "show", "musica")] + verify.canvas_act("canvas:close:youtube", 3)
    assert verify.canvas_now(evs) == ["musica"]
    assert verify.canvas_act("music", 3) == []
