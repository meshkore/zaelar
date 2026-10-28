"""An order the action map answers is heard by the use-case tester (2026-10-27).

The old probe channel returned its reply as a list of SENTENCES (`["Listo."]`). The runner
flattened replies with `llm._as_text`, which only knew a provider's list of PARTS (`[{"type": "text", …}]`) and
dropped every plain string. So every order the action map resolved without a model — «Sal de pantalla completa»
answered «Listo.» in 3 ms, read from the sandbox's own log — was recorded as a mute turn: the tester asked «¿me has
oído?», the conversation went sideways, and `video-exit-fullscreen-unnamed` scored 1/5 for a silence the product
never had. The engine's real lanes are asked here for their shape, not a hand-written copy of it.
"""
from __future__ import annotations

from tests.use_cases.e2e.agent import llm


def test_the_engines_list_of_sentences_reads_as_what_it_said():
    assert llm._as_text(["Listo."]) == "Listo."
    assert llm._as_text(["Hecho.", "Te lo dejo en pantalla."]) == "Hecho. Te lo dejo en pantalla."


def test_the_action_map_lane_reply_survives_the_runner(monkeypatch):
    """The suite's workspace has no seeded map: the HIT is fixed, and the canvas reports a card at full screen so the
    map's `unfullscreen` has a target. The typed turn's own reply is what the runner reads."""
    import asyncio

    from memory import api as memapi
    from nucleo import actionmap as amap
    from nucleo.cli import turn as cli_turn
    monkeypatch.setattr(amap, "enabled", lambda: True)
    monkeypatch.setattr(amap, "match_spoken", lambda text: {"id": 129, "action": {"do": "unfullscreen"}})
    monkeypatch.setattr(amap, "record_hit", lambda i: None)
    real_state = memapi.state
    monkeypatch.setattr(memapi, "state", lambda *a, **k: {**(real_state(*a, **k) or {}), "maximized_widget": "youtube"})
    cli_turn.reset("amap-heard")
    try:
        got = asyncio.run(cli_turn.run_turn("Sal de pantalla completa.", sid="amap-heard", ingest=False, execute=False))
    finally:
        cli_turn.reset("amap-heard")
    assert got["ok"] and got["action"] == "canvas:unfullscreen", got
    assert llm._as_text(got["reply"]).strip(), f"the runner reads {got['reply']!r} as silence"


def test_a_providers_parts_still_concatenate_and_drop_non_text():
    parts = [{"type": "text", "text": "Hola"}, {"type": "image_url", "image_url": {}}, {"type": "text", "text": " mundo"}]
    assert llm._as_text(parts) == "Hola mundo"
    assert llm._as_text(None) == ""
