"""«cierra el vídeo … La agenda la miro luego» closes the PLAYER on both channels (`tres-tarjetas-y-el-video-por-
alusion`, ES, report 2026-10-14 00:37, t6 → `canvas:close:agenda`).

The verdict gesture (`card_close.run_gesture`, the voice `direct_action.complete_canvas` and the text
`card_close.complete_canvas_mirror`) let the agenda — named by its catalogue name only inside the deferral — beat the
verdict's `youtube:close`, whatever card the verdict proposed.
"""
from __future__ import annotations

import pytest

from nucleo.flash import card_close
from tests.agent_headless.unit.flash.test_a_card_he_keeps_is_never_closed import (  # noqa: F401 — fixtures
    _brief, _gesture, screen, spanish)

T6 = "Perfecto, cierra el vídeo y deja la música sonando de fondo, porfa. La agenda la miro luego."


@pytest.mark.parametrize("verdict, conf", [("youtube:close", 1.0), ("youtube:close", 0.5), ("agenda:close", 0.6),
                                           ("", 0.0)])
def test_the_voice_gesture_closes_the_video_only(screen, spanish, verdict, conf):
    assert _gesture(_brief(verdict, conf), T6) == [("close", "youtube")]


def test_the_text_mirror_closes_the_video_only(screen, spanish):
    got = card_close.complete_canvas_mirror(_brief("youtube:close", 1.0), T6, blocked=False)
    assert got.get("action") == "canvas:close:youtube"


def test_the_english_deferral_closes_the_video_only(screen):
    text = "ok, close the video and leave the music on. I'll check the calendar later."
    assert _gesture(_brief("youtube:close", 0.6), text) == [("close", "youtube")]
