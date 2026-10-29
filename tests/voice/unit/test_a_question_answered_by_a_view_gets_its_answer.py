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
    from nucleo.turn import brief as tb
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


def test_an_order_that_owes_words_is_answered_too(monkeypatch):
    """R3 «find me five days in her vacation where i'm free and tell me the dates» and M1 «how's apple stock doing
    today, show me the chart» read as ORDERS and got a view and silence. The brief's `wants_words` question (live:
    14/15 over the demo's phrases) says when an order owes an answer."""
    from nucleo.flash import card_commission as cc, widget_read
    from nucleo.turn import brief as tb
    monkeypatch.setattr(widget_read, "can_answer", lambda w: True)
    b = _brief("order")
    b["result"][tb.WORDS_KEY] = {"choice": "tell", "confidence": 0.95}
    assert cc.question_left_to_a_lens(b, ops=[{"widget_id": "markets", "action": "show"}], acted={}) == "markets"
    b["result"][tb.WORDS_KEY] = {"choice": "act", "confidence": 0.95}
    assert cc.question_left_to_a_lens(b, ops=[{"widget_id": "youtube", "action": "show_tab"}], acted={}) == ""
    assert tb.WORDS_KEY in tb.build("find me five days and tell me the dates")


def test_a_data_op_that_answers_is_the_answer(monkeypatch):
    """Demo pass 2026-09-28 (E block, isolated): «check my email, did inworld send me something?» — the model called
    search_archive, it found the Inworld invoice, and the turn said «Let me check your inbox»: the voice path
    dispatches detached and only ever read a result that FAILED. A turn that owes words waits for its ops (bounded)
    and answers with what they returned."""
    from nucleo.flash import data_ops as d
    assert d.answer_of({"ok": True, "queued": True, "id": "mensajeria", "matches": [{"from": "Inworld AI"}]}) == \
        {"matches": [{"from": "Inworld AI"}]}
    assert d.answer_of({"ok": True, "queued": True, "id": "mensajeria"}) == {}
    assert d.answer_of({"ok": False, "error": "x", "matches": [1]}) == {}
    said = _ops_answer_door(monkeypatch, {"ok": True, "queued": True, "id": "mensajeria",
                                          "matches": [{"from": "Inworld AI"}]}, "mensajeria", "search_archive")
    assert said and "Inworld AI" in said[0]["system"] and said[0]["label"] == "op answer compose"
    src = (ROOT / "nucleo/flash/data_ops.py").read_text("utf-8")
    assert "return res          # the RESULT" in src


def test_the_answer_knows_the_card_it_came_from_is_on_screen(monkeypatch):
    """Demo pass 2026-09-28 (full13 M1): «how's apple stock doing today, show me the chart» — the chart was on
    screen and the answer composed from the op's data said «I can't pull up a chart for you here». The second
    pass saw the numbers and not the card: an open card is part of what it answers with."""
    from pathlib import Path
    from nucleo.flash import widget_read
    on = widget_read.compose_system("L", "show me the chart", "markets", "q", "AAPL 341", answered=True, on_screen=True)
    off = widget_read.compose_system("L", "show me the chart", "markets", "q", "AAPL 341", answered=True)
    assert "YA ESTÁ ABIERTA" in on and "YA ESTÁ ABIERTA" not in off
    from nucleo.flash import post_stream as pst
    for shown in (True, False):
        monkeypatch.setattr(pst._direct_action, "on_screen_now", lambda wid, _s=shown: _s and wid == "markets")
        said = _ops_answer_door(monkeypatch, {"ok": True, "quote": "AAPL 341"}, "markets", "quote")
        assert said and said[0]["on_screen"] is shown, "report OR this turn (full17 M1)"


def _ops_answer_door(monkeypatch, result, wid, action, kind="question"):
    """Run the turn's ONE op-answer door (`post_stream_acts.speak_the_ops_answer`) over one op that returned `result`;
    returns what it handed the second pass (system prompt, label, on_screen) — [] when it said nothing."""
    import asyncio
    from nucleo.flash import post_stream_acts as psa, widget_read
    seen: list[dict] = []
    real = widget_read.op_answer_system

    def _system(*a, on_screen=False, **k):
        seen.append({"on_screen": on_screen})
        return real(*a, on_screen=on_screen, **k)
    monkeypatch.setattr(widget_read, "op_answer_system", _system)

    async def _speak(system, text, cap, label, **_k):
        seen[-1].update({"system": system, "label": label})

    class _Prompt:
        @staticmethod
        def _lang_lock():
            return "L"

    async def _go():
        fut = asyncio.get_running_loop().create_future()
        fut.set_result(result)
        return await psa.speak_the_ops_answer(
            _brief=_brief(kind), _op_text="did inworld send me something?", _turn_op_tasks=[(wid, fut)],
            data_done={"ops": [(wid, action)]}, read_req={"v": None}, escalate_req={"v": None},
            search_req={"v": None}, speak=_speak, emit=lambda *a, **k: None, _prompt_mod=_Prompt)
    spoke = asyncio.run(_go())
    return seen if spoke else []
