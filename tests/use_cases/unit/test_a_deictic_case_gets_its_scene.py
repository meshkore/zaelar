"""A case whose opening points at the screen («Bloquéame este canal») gets that screen seeded first.

`video-blocked-channel-respected` (2026-10-10) ran on an empty player: the agent said there was no channel in
front of it, the tester invented one, and both rounds measured the invention. `card_seed` writes the scene through
the widget's own store in the sandbox, and the judge is told what was on screen.
"""
import json
from types import SimpleNamespace

from tests.use_cases.e2e.agent import card_seed, errand_seed


def test_the_case_declares_a_playing_video_and_suggestions_of_its_channel():
    scene = card_seed.scene_for("video-blocked-channel-respected__us")
    assert scene["channel"] == card_seed.BLOCKED and scene["videoId"]
    assert sum(s["channel"] == card_seed.BLOCKED for s in scene["suggested"]) == 1 and len(scene["suggested"]) == 3
    assert card_seed.scene_for("video-search-lands-in-player__es") == {}


def test_the_scene_lands_in_the_sandbox_store_and_the_pointer_resolves_against_it(tmp_path):
    got = card_seed.sow(str(tmp_path), card_seed.scene_for("video-blocked-channel-respected"))
    assert got == {"channel": card_seed.BLOCKED, "suggested": 3}
    state = json.loads((tmp_path / "widgets" / "_data" / "youtube" / "state.json").read_text(encoding="utf-8"))
    assert state["videoId"] == "dQw4w9WgXcQ"


def test_a_case_without_a_scene_seeds_nothing_and_the_note_names_the_scene():
    assert errand_seed.step(SimpleNamespace(id="video-search-lands-in-player__es", locale="es"), "") == {}
    note = errand_seed.judge_note({"seeded": [], "card": {"seeded": True, "channel": card_seed.BLOCKED}})
    assert "TARJETA SEMBRADA" in note and card_seed.BLOCKED in note and "ENCARGOS" not in note
    assert "FALLÓ" in errand_seed.judge_note({"seeded": [], "card": {"seeded": False, "error": "x"}})
