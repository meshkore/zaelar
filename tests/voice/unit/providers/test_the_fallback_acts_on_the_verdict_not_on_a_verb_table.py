"""The widget fallback acts on the turn's canvas VERDICT, never on a verb stem plus a catalogue noun (V2-807 T-07).

Measured: while he corrected a draft's signature — «put the .com website in too… this message doesn't look right» —
the messaging card opened by itself. The fallback matched the open stem «pon» and `identify` found the messaging
card through its nouns («firma», «mensaje»); the turn's own verdict was `canvas=neither` at 0.96 and nobody read it.

The class: a verb-stem table plus a catalogue-noun match is not an order. The fallback acts only on a SURE canvas
verdict; a show also needs a card his words NAME (never one found «by context»). Absent or unsure verdict → nothing.
"""
from __future__ import annotations

import threading


from voice.engine.llm.providers import widget_intent as WI


def _brief(canvas, conf=0.96):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": [], "result": {"canvas": {"choice": canvas, "confidence": conf}}}


def _collect():
    events: list[tuple] = []

    def emit(kind, action, text=None, role=None, extra=None):
        events.append((kind, action, dict(extra or {})))
    return events, emit


SIGNATURE_EDITS = [
    "Nombre completo está bien, y pon también la web de punto com",
    "¿Puedes poner los interlineados? No queda bien este mensaje con la firma",
    "Put the dot-com website in the signature of this message too",
    "署名にウェブサイトも入れて、このメッセージはよくない",
]


def test_the_turn_passes_its_brief_to_the_fallback():
    from pathlib import Path
    src = Path(WI.__file__).resolve().parents[4] / "nucleo/turn/pipeline_close.py"   # V2-851 F5: the turn's close
    assert "brief=_brief):" in src.read_text(encoding="utf-8").split("motor._widget_fallback(", 1)[1][:260]
