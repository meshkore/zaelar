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
    assert "_cardc3.question_left_to_a_lens(_brief, ops=list(_data_ops_hechas), acted=acted," in prov
    body = prov[prov.index("async def speak(sys2: str"):]
    body = body[:body.index("from voice.engine.llm.providers.vault_intercept")]
    assert "responde exactamente SKIP" in body and 'head.startswith("SKIP")' in body


def test_an_order_that_owes_words_is_answered_too(monkeypatch):
    """R3 «find me five days in her vacation where i'm free and tell me the dates» and M1 «how's apple stock doing
    today, show me the chart» read as ORDERS and got a view and silence. The brief's `wants_words` question (live:
    14/15 over the demo's phrases) says when an order owes an answer."""
    from nucleo.flash import card_commission as cc, turn_brief as tb, widget_read
    monkeypatch.setattr(widget_read, "can_answer", lambda w: True)
    b = _brief("order")
    b["result"][tb.WORDS_KEY] = {"choice": "tell", "confidence": 0.95}
    assert cc.question_left_to_a_lens(b, ops=[{"widget_id": "markets", "action": "show"}], acted={}) == "markets"
    b["result"][tb.WORDS_KEY] = {"choice": "act", "confidence": 0.95}
    assert cc.question_left_to_a_lens(b, ops=[{"widget_id": "youtube", "action": "show_tab"}], acted={}) == ""
    assert tb.WORDS_KEY in tb.build("find me five days and tell me the dates")


def test_a_read_of_a_card_this_turn_changed_waits_for_the_change():
    """full11 M3: «and the nasdaq, over the whole year» switched the chart and the read, a few ms later, answered
    «the only thing on the chart is Apple — I've got no Nasdaq figures». The read waits (bounded) for this turn's
    dispatches to the same card."""
    prov = (ROOT / "voice/engine/llm/providers/nucleo.py").read_text("utf-8")
    assert "_op_task = _data_ops.start_op(" in prov and "_turn_op_tasks.append((wid, _op_task))" in prov
    i = prov.index("_pending = [t for w, t in _turn_op_tasks")
    assert i < prov.index("await speak(await _wread.prepare(read_req", i)
    assert "await asyncio.wait(_pending, timeout=6.0)" in prov


def test_a_data_op_that_answers_is_the_answer():
    """Demo pass 2026-09-28 (E block, isolated): «check my email, did inworld send me something?» — the model called
    search_archive, it found the Inworld receipt, and the turn said «Let me check your inbox»: the voice path
    dispatches detached and only ever read a result that FAILED. A turn that owes words waits for its ops (bounded)
    and answers with what they returned."""
    from nucleo.flash import data_ops as d
    assert d.answer_of({"ok": True, "queued": True, "id": "mensajeria", "matches": [{"from": "Inworld AI"}]}) == \
        {"matches": [{"from": "Inworld AI"}]}
    assert d.answer_of({"ok": True, "queued": True, "id": "mensajeria"}) == {}
    assert d.answer_of({"ok": False, "error": "x", "matches": [1]}) == {}
    prov = (ROOT / "voice/engine/llm/providers/nucleo.py").read_text("utf-8")
    assert "_data_ops.answer_of(_t.result())" in prov and "op answer compose" in prov
    src = (ROOT / "nucleo/flash/data_ops.py").read_text("utf-8")
    assert "return res          # the RESULT" in src


def test_the_answer_knows_the_card_it_came_from_is_on_screen():
    """Demo pass 2026-09-28 (full13 M1): «how's apple stock doing today, show me the chart» — the chart was on
    screen and the answer composed from the op's data said «I can't pull up a chart for you here». The second
    pass saw the numbers and not the card: an open card is part of what it answers with."""
    from pathlib import Path
    from nucleo.flash import widget_read
    on = widget_read.compose_system("L", "show me the chart", "markets", "q", "AAPL 341", answered=True, on_screen=True)
    off = widget_read.compose_system("L", "show me the chart", "markets", "q", "AAPL 341", answered=True)
    assert "YA ESTÁ ABIERTA" in on and "YA ESTÁ ABIERTA" not in off
    prov = (Path(__file__).resolve().parents[3] / "voice/engine/llm/providers/nucleo.py").read_text("utf-8")
    assert "on_screen=_direct_action.on_screen_now(_op_answer[0])" in prov, "report OR this turn (full17 M1)"


def test_the_card_that_answered_wins_over_a_web_search_in_the_same_turn():
    """Demo pass 2026-09-28 (full15 M1): «how's apple stock doing today, show me the chart» — the model called
    `markets:show` AND `web_search`; the chart came with its price, and the search answered «the search results
    only gave me quote pages, so I can't tell you». The card of this turn is the source; the search does not run."""
    from pathlib import Path
    prov = (Path(__file__).resolve().parents[3] / "voice/engine/llm/providers/nucleo.py").read_text("utf-8")
    block = prov.split("_op_answer = None", 1)[1].split("A QUESTION answered by a lens alone", 1)[0]
    assert 'search_req["v"] is None and _turn_op_tasks' not in block, "a search must not keep the card from answering"
    assert 'if _op_answer is not None and search_req["v"] is not None' in block and 'search_req["v"] = None' in block
