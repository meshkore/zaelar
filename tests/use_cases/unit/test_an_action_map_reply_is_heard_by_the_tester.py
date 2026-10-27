"""An order the action map answers is heard by the use-case tester (2026-10-27).

The probe channel returns its reply as a list of SENTENCES (`["Listo."]`, `nucleo/flash/probe_api.py`). The runner
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
    """The suite's workspace has no seeded map: the HIT is fixed, the lane's own reply shape is what is read."""
    from nucleo import actionmap as amap
    from nucleo.flash import probe_actionmap as pa
    from voice.engine.core import langs
    monkeypatch.setattr(amap, "enabled", lambda: True)
    monkeypatch.setattr(amap, "match_spoken", lambda text: {"id": 129, "action": {"do": "unfullscreen"}})
    monkeypatch.setattr(amap, "record_hit", lambda i: None)

    class _Sess:
        window: list = []
        smalltalk_bounce = False

    got = pa.try_map("Sal de pantalla completa.", _Sess(), execute=False, trace_id="t", pick_ack=langs.pick_ack)
    assert got is not None and isinstance(got["reply"], list) and got["reply"], got
    assert llm._as_text(got["reply"]).strip(), f"the runner reads {got['reply']!r} as silence"


def test_a_providers_parts_still_concatenate_and_drop_non_text():
    parts = [{"type": "text", "text": "Hola"}, {"type": "image_url", "image_url": {}}, {"type": "text", "text": " mundo"}]
    assert llm._as_text(parts) == "Hola mundo"
    assert llm._as_text(None) == ""
