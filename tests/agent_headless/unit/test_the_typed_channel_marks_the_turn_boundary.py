# Demo pass in a sandbox through the typed channel, 2026-10-28 — A2 «ok just put that away for now while you work on
# it» (canvas=minimize at 1.00) and V4 «go back to normal size» (exit_fullscreen at 1.00): neither gesture found the
# card «that» meant. `canvas_focus` answers «the card his previous turn acted on» from a window it rotates on the
# voice's final transcript (`transcript`, role user). The typed channel (`nucleo/cli/turn.run_turn`: the probe, the
# decision bank, the lab, a sandbox) emits no transcript — on purpose, the frontend's voice fast path executes that
# event — so through it the window never rotated: every turn's touches piled into one «current» window and
# «previous» stayed empty for the life of the process. An unnamed order then fell to «the only one open», and with
# two cards open found nothing. A rule that lived on one of two channels (the class refactor2710 names).
#
# THE CLASS: the turn boundary is the TURN's, not an event's. `canvas_focus.begin_turn` is the one boundary; the
# voice reaches it through its transcript, the typed channel calls it as the turn starts.
from __future__ import annotations

import asyncio

import pytest

from nucleo import canvas_focus as cf


@pytest.fixture(autouse=True)
def _clean():
    cf._reset()
    yield
    cf._reset()


def test_a_turn_boundary_makes_the_touches_so_far_the_previous_turn():
    cf.begin_turn()
    cf.note("widget", "show", extra={"id": "results::ab19a4-1", "src": "worker:ab19a4-1"})
    assert cf.last_turn_card(["agenda", "results::ab19a4-1"]) == "", "still this turn's touches, not the previous"
    cf.begin_turn()
    assert cf.last_turn_card(["agenda", "results::ab19a4-1"]) == "results::ab19a4-1"


def test_the_voices_transcript_and_the_typed_boundary_are_one_boundary():
    cf.note("transcript", "🗣", role="user")
    cf.note("widget", "data:play_result", extra={"id": "youtube", "src": "flash"})
    cf.begin_turn()
    assert cf.last_turn_card(["youtube", "mensajeria"]) == "youtube"
    cf.note("transcript", "🗣", role="user")       # a boundary over an untouched turn keeps the previous window
    assert cf.last_turn_card(["youtube", "mensajeria"]) == "youtube"


def test_the_typed_channel_rotates_the_window_as_its_turn_starts(monkeypatch):
    """`run_turn` crosses the boundary before the turn's doors read «the card his previous turn acted on»."""
    from nucleo.cli import turn as cli_turn
    from voice import typed_turn
    cf.begin_turn()
    cf.note("widget", "show", extra={"id": "results::ab19a4-1", "src": "worker:ab19a4-1"})
    seen = {}

    async def _drive(brain, text):
        seen["focus"] = cf.last_turn_card(["mensajeria", "results::ab19a4-1"])
        return "stashed"
    monkeypatch.setattr(typed_turn, "drive", _drive)
    out = asyncio.run(cli_turn.run_turn("ok just put that away for now while you work on it", sid="boundary-test",
                                        ingest=False))
    assert out.get("ok") is True, out
    assert seen["focus"] == "results::ab19a4-1", seen
