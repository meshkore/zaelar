"""Demo pass 2026-09-28: «johnny what do i have tomorrow» → `agenda:show_day` and silence (C1); «what's on my plate
tomorrow» → «Let me pull your day up.» and the same view, no answer (Z1). A view is where he LOOKS; a question wants
the answer said. When the verdict reads a QUESTION and everything the turn did was a lens, the card is read and the
answer composed — and that second pass, told what was already said, answers SKIP (held back, never spoken) when it
already answered. Measured live: «Let me pull your day up.» → the four meetings 2/2; a full answer → SKIP, or only
the meeting it had left out."""
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _brief(kind):
    from nucleo.flash import turn_brief as tb
    ev = threading.Event(); ev.set()
    return {"event": ev, "turn_id": "t", "open_ids": ["agenda"],
            "result": {tb.REQUEST_KEY: {"choice": kind, "confidence": 0.9}}}


def test_a_question_whose_turn_only_looked_reads_the_card(monkeypatch):
    from nucleo.flash import card_commission as cc, widget_read
    monkeypatch.setattr(widget_read, "can_answer", lambda w: True)
    ops = [{"widget_id": "agenda", "action": "show_day", "payload": {"date": "2026-09-29"}}]
    assert cc.question_left_to_a_lens(_brief("question"), ops=ops, acted={}) == "agenda"
    assert cc.question_left_to_a_lens(_brief("question"), ops=[], acted={"widget_id": "agenda"}) == "agenda"


def test_an_order_or_a_write_is_not_this(monkeypatch):
    from nucleo.flash import card_commission as cc, widget_read
    monkeypatch.setattr(widget_read, "can_answer", lambda w: True)
    view = [{"widget_id": "agenda", "action": "show_day"}]
    write = [{"widget_id": "agenda", "action": "add_meeting"}]
    assert cc.question_left_to_a_lens(_brief("order"), ops=view, acted={}) == ""
    assert cc.question_left_to_a_lens(_brief("question"), ops=write, acted={}) == ""


def test_the_second_pass_can_stay_silent_and_the_provider_wires_it():
    prov = (ROOT / "voice/engine/llm/providers/nucleo.py").read_text("utf-8")
    assert "_cardc3.question_left_to_a_lens(_brief, ops=list(_data_ops_hechas), acted=acted)" in prov
    body = prov[prov.index("async def speak(sys2: str"):]
    body = body[:body.index("from voice.engine.llm.providers.vault_intercept")]
    assert "responde exactamente SKIP" in body and 'head.startswith("SKIP")' in body
