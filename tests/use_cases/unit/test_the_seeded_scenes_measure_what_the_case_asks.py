"""Node 2.718 — the seeded video scenes put on screen what each case's sentence points at (2026-10-14).

Two rounds measured a premise the sandbox did not hold:

  · `video-blocked-channel-respected` (ES+EN 3/5): the link the tester pasted was the video ALREADY playing, so EN
    «play» became an unmute and ES an `add` deduped against it — no round ever let a NEW link from the blocked channel
    through. The pasted link is now another video of that channel, which his history already names.
  · `video-exit-fullscreen-unnamed` (EN 2/5, ES passed on an empty screen too): neither round seeded a card, so
    «Exit full screen» ran on an empty canvas. The scene now opens the player MAXIMIZED, and the round takes it out
    of full screen when the turn's action does, as the desktop would.

Disarm: point `PASTED_LINK` back at the playing video → the first test goes red; empty `MAXIMIZED` → the full-screen
tests go red.
"""
from tests.use_cases.e2e.agent import card_seed
from tests.use_cases.e2e.agent.derived import PROFILES
from widgets.youtube.helpers import _extract_id


def test_the_pasted_link_is_another_video_of_the_blocked_channel_his_history_names():
    scene = card_seed.scene_for("video-blocked-channel-respected__es")
    pasted = _extract_id(card_seed.PASTED_LINK)
    assert pasted and pasted != scene["videoId"]
    assert [h["channel"] for h in scene["history"] if h["videoId"] == pasted] == [card_seed.BLOCKED]
    prof = PROFILES["video-blocked-channel-respected"]
    assert card_seed.PASTED_LINK in prof.persona_extra and card_seed.PASTED_LINK in prof.persona_extra_us


def test_the_full_screen_case_seeds_a_maximized_player(tmp_path):
    case = "video-exit-fullscreen-unnamed__us"
    assert card_seed.card_for(case) == "youtube" and card_seed.scene_for(case)["videoId"]
    assert card_seed.canvas_report(case, "youtube") == {"open": ["youtube"], "layout": [{"id": "youtube", "max": "1"}]}
    assert card_seed.sow(str(tmp_path), card_seed.scene_for(case))["channel"] == card_seed.BLOCKED


def test_the_round_takes_the_card_out_of_full_screen_as_the_desktop_would():
    case = "video-exit-fullscreen-unnamed__es"
    out = card_seed.after_turn(case, "youtube", "canvas:unfullscreen:youtube")
    assert out == {"open": ["youtube"], "layout": [{"id": "youtube"}]}
    assert card_seed.after_turn(case, "youtube", "chat") is None
    assert card_seed.after_turn("video-blocked-channel-respected__es", "youtube", "canvas:unfullscreen:") is None


def test_the_judge_is_told_the_card_was_at_full_screen():
    note = card_seed.judge_note({"seeded": True, "card": "youtube", "channel": card_seed.BLOCKED, "maximized": True})
    assert "PANTALLA COMPLETA" in note
