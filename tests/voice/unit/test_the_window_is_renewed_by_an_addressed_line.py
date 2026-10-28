"""V2-812 T-03 — inside the attention window a line is still JUDGED, the window is renewed only by an addressed
line, and a side effect from a line that was not a clear request to the agent asks first.

Measured in a car (session e52cd845, «always» mode, 30 s window): 68 of 68 lines admitted, about half of them
talk between the passengers; every handled line renewed the window, so it could not die while anybody spoke;
and «Eso es.», said after a sentence that stated something AND offered to resume a failed booking, resumed it.

The window still admits without waiting for the judge (deafness inside a conversation is the failure this
module has paid for three times), so what is tested is what an admitted line CAN DO once judged:
  · renew the window (its admission, the reply's chunks, the reply's falling edge) — only if addressed;
  · start an act that leaves, or a worker, without asking — only if it was a clear request.
And the other side of the bargain: a lone operator talking to the agent is never asked anything new, and a wake
word or a typed line is never judged at all. Spanish and English variants of every case.
"""
from __future__ import annotations

import asyncio

import pytest

from voice import attention, attention_lines
from voice import trace as _trace

CAR = {
    "es": {"addressed": ("Ponnos música de Shakira.", "Suena Dai Dai — Shakira."),
           "side": ("Ostras, tenéis que sacar las maletas. ¿No?", "Suena Dai Dai — Shakira."),
           "assent": ("Eso es.", "Sí, te he oído: paro con la música. ¿Quieres que retome la reserva?")},
    "en": {"addressed": ("Play us some Shakira.", "Playing Dai Dai — Shakira."),
           "side": ("Kids, you have to take the suitcases out, right?", "Playing Dai Dai — Shakira."),
           "assent": ("That's it.", "Yes, I heard you: stopping the music. Shall I resume the booking?")},
}
LONE = {
    "es": ["Pon música de Rosalía.", "Súbele el volumen.", "¿Qué tengo mañana?", "Mándale a Marta que llego tarde.",
           "Sí, mándalo.", "Búscame vuelos a Lisboa para el viernes."],
    "en": ["Play some Taylor Swift.", "Turn it up.", "What do I have tomorrow?", "Tell Marta I'm running late.",
           "Yes, send it.", "Find me flights to Lisbon on Friday."],
}


@pytest.fixture(autouse=True)
def _always(monkeypatch):
    monkeypatch.setenv("ZAELAR_ATTENTION", "always")
    monkeypatch.delenv("ZAELAR_ATTENTION_WINDOW", raising=False)
    attention.reset()
    attention.set_directed_judge(None)
    yield
    attention.set_directed_judge(None)
    attention.reset()
    _trace.adopt("")


def _judge_says(table: dict):
    """A judge double answering by line — the verdict the real judge returned on the same lines (V2-812)."""
    async def _judge(text, context):
        return table[text]
    return _judge


def _admit(text: str, *, context: str, now: float, trace: str):
    """The gate's caller, as `attention_turn.judge` runs it: evaluate, register the line, renew, and let the
    judgement beside the turn land."""
    async def go():
        _trace.adopt(trace)
        v = await attention.evaluate_content(text, context=context, now=now)
        assert v.directed, f"a line inside the window must still be admitted: «{text}»"
        attention.open_line(v, text=text, context=context, now=now)
        attention.note_directed(now=now)
        await asyncio.gather(*list(attention_lines._JUDGE_TASKS))
        return v
    return asyncio.run(go())


@pytest.mark.parametrize("lang", ["es", "en"])
def test_talk_between_passengers_is_admitted_but_does_not_keep_the_window_open(lang):
    addressed, ctx = CAR[lang]["addressed"]
    side, ctx2 = CAR[lang]["side"]
    attention.set_directed_judge(_judge_says({side: {"directed": False, "request": False}}))
    t0 = 1000.0
    attention.note_directed(now=t0)                         # his order opened the conversation (wake word, say)
    attention.open_line(attention.Verdict(True, "wakeword", by_act=True), text=addressed, trace="T1", now=t0)
    v = _admit(side, context=ctx2, now=t0 + 10, trace="T2")
    assert v.reason == "active_window"
    assert attention._state["last_directed"] == t0, "a line judged not addressed gave its renewal back"
    # The reply to it is not conversation with HIM either: its chunks renew nothing…
    _trace.adopt("T2")
    attention.note_directed(now=t0 + 12)
    assert attention._state["last_directed"] == t0, "the reply to talk between passengers renewed the window"
    # …and neither does its falling edge.
    attention.note_bot_speech(True, now=t0 + 12)
    attention.note_bot_speech(False, now=t0 + 15)
    assert attention._state["last_directed"] == t0, "the agent's own mouth re-anchored a window nobody opened"
    assert attention.window_warm(now=t0 + 29)
    assert not attention.window_warm(now=t0 + 31), "the window must die 30 s after the last ADDRESSED exchange"
    assert attention.licence("T2") is False


@pytest.mark.parametrize("lang", ["es", "en"])
def test_an_addressed_line_inside_the_window_renews_it(lang):
    addressed, ctx = CAR[lang]["addressed"]
    attention.set_directed_judge(_judge_says({addressed: {"directed": True, "request": True}}))
    t0 = 1000.0
    attention.note_directed(now=t0)
    _admit(addressed, context=ctx, now=t0 + 20, trace="T3")
    assert attention._state["last_directed"] == t0 + 20
    _trace.adopt("T3")
    attention.note_directed(now=t0 + 22)                    # the reply's chunk
    assert attention._state["last_directed"] == t0 + 22
    assert attention.licence("T3") is True


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_lone_operator_is_never_asked_anything_new(lang):
    """The quiet room: everything he says is for the agent and every order is a request. Nothing renews less,
    nothing licenses less, and an act that leaves runs exactly as before."""
    from nucleo import consent
    lines = LONE[lang]
    attention.set_directed_judge(_judge_says({t: {"directed": True, "request": True} for t in lines}))
    t0 = 1000.0
    attention.note_directed(now=t0)
    for i, text in enumerate(lines, 1):
        now = t0 + 8 * i
        v = _admit(text, context="ok", now=now, trace=f"L{i}")
        assert v.reason == "active_window"
        assert attention._state["last_directed"] == now, f"his own line did not renew the window: «{text}»"
        _trace.adopt(f"L{i}")
        assert consent.decide(level="standard", policy_key="messaging.send_new")["verdict"] == consent.RUN, \
            f"his own clear order was asked about: «{text}»"


@pytest.mark.parametrize("lang", ["es", "en"])
def test_an_assent_after_an_offer_starts_nothing_without_asking(lang):
    from nucleo import consent
    assent, ctx = CAR[lang]["assent"]
    attention.set_directed_judge(_judge_says({assent: {"directed": True, "request": False}}))
    t0 = 1000.0
    attention.note_directed(now=t0)
    _admit(assent, context=ctx, now=t0 + 5, trace="T4")
    assert attention._state["last_directed"] == t0 + 5, "an addressed line renews the window"
    _trace.adopt("T4")
    v = consent.decide(level="standard", policy_key="messaging.send_new", his_yes=True)
    assert v["verdict"] == consent.ASK_CONSENT and v.get("unlicensed"), \
        "an act that leaves ran from a line that was not a request — and his_yes may not clear it"
    # A plain data-op on a card (standard, no consent class) is not an act that leaves: unchanged.
    assert not consent.decide(level="standard").get("unlicensed")


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_wake_word_and_a_typed_line_are_never_judged(lang):
    async def _judge(text, context):
        raise AssertionError("a line addressed by an act of his is never judged")
    attention.set_directed_judge(_judge)
    text = "Johnny, pon música" if lang == "es" else "Johnny, play some music"
    attention.set_assistant_name("Johnny")

    async def go():
        _trace.adopt("W1")
        v = await attention.evaluate_content(text, context="ok", now=1000.0)
        attention.open_line(v, text=text, now=1000.0)
        await asyncio.gather(*list(attention_lines._JUDGE_TASKS))
        return v
    assert asyncio.run(go()).reason == "wakeword"
    assert attention.licence("W1") is None, "a wake word licenses nothing new: unknown keeps today's path"
    typed = "apúntame pan" if lang == "es" else "add bread to my list"
    attention.note_directed(now=2000.0)
    attention.note_typed(now=2000.0, text=typed)

    async def go2():
        _trace.adopt("Y1")
        v = await attention.evaluate_content(typed, context="ok", now=2000.0)
        attention.open_line(v, text=typed, now=2000.0)
        await asyncio.gather(*list(attention_lines._JUDGE_TASKS))
    asyncio.run(go2())
    assert attention_lines._LINES["Y1"]["addressed"] is True and attention.licence("Y1") is None
    attention.set_assistant_name("")


def test_a_failed_judge_leaves_the_line_as_admitted():
    async def _judge(text, context):
        raise RuntimeError("provider down")
    attention.set_directed_judge(_judge)
    attention.note_directed(now=1000.0)
    _admit("algo", context="ok", now=1005.0, trace="F1")
    assert attention._state["last_directed"] == 1005.0
    assert attention.licence("F1") is None


def test_an_armed_delivery_still_reanchors_after_an_unaddressed_line():
    attention.set_directed_judge(_judge_says({"bla": {"directed": False, "request": False}}))
    attention.note_directed(now=1000.0)
    _admit("bla", context="ok", now=1005.0, trace="D1")
    attention.note_addressed_speech(now=1010.0)               # a finished errand is about to speak to him
    attention.note_bot_speech(True, now=1010.0)
    attention.note_bot_speech(False, now=1020.0)
    assert attention._state["last_directed"] == 1020.0, "a delivery owed to him opens the window it always did"


def test_the_judge_answers_both_questions_and_old_shapes_still_parse():
    assert attention._parse_judgement('{"directed": true, "request": false}') == {"directed": True, "request": False}
    assert attention._parse_judgement('```json\n{"directed": false}\n```') == {"directed": False, "request": None}
    assert attention._parse_directed('{"directed": true, "request": true}') is True
    assert attention._as_judgement(True) == (True, None)
    assert attention._as_judgement({"directed": True, "request": False}) == (True, False)
    assert '"request"' in attention._DIRECTED_SYSTEM


# ── the one door a worker starts through ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("lang", ["es", "en"])
def test_an_errand_from_an_assent_is_parked_on_a_question_in_his_language(lang, monkeypatch):
    from i18n import langs
    from nucleo import dispatch
    from nucleo.dispatch import confirm as dispatch_confirm
    monkeypatch.setattr(langs, "current_language", lambda: langs.spec(lang))
    dispatch._PENDING_CONFIRM.clear()
    attention_lines._LINES["T9"] = {"key": "T9", "text": "Eso es.", "at": 0.0, "anchor": 0.0, "recent": [],
                              "reason": "active_window", "addressed": True, "request": False, "pending": False,
                              "granted": False}
    req = "Resume yesterday's restaurant booking for two"
    task = dispatch.Task(id="77", request=req, context={"trace": "T9"})
    parked = asyncio.run(dispatch_confirm.unlicensed_gate(task, "77", req, wait_s=0.0))
    assert parked, "a worker started from a line that was not a request"
    p = dispatch._PENDING_CONFIRM.get("77")
    assert p and p.get("unlicensed") and p.get("offered")
    assert p["question"] == langs.spec(lang).errand_unaddressed_confirm.format(what=req)
    assert langs.spec(lang).errand_unaddressed_confirm, f"no question in {lang}"
    # His YES relaunches through the same door with `confirmed`: it runs, and the line is his from now on.
    task2 = dispatch.Task(id="78", request=req, context={"trace": "T9", "confirmed": True})
    assert not asyncio.run(dispatch_confirm.unlicensed_gate(task2, "78", req, wait_s=0.0))
    assert attention.licence("T9") is True
    dispatch._PENDING_CONFIRM.clear()


def test_an_errand_from_a_request_or_with_no_line_runs():
    from nucleo import dispatch
    from nucleo.dispatch import confirm as dispatch_confirm
    attention_lines._LINES["T10"] = {"key": "T10", "text": "x", "at": 0.0, "anchor": 0.0, "recent": [],
                               "reason": "always", "addressed": True, "request": True, "pending": False,
                               "granted": False}
    for ctx in ({"trace": "T10"}, {"trace": "unknown"}, {}):
        task = dispatch.Task(id="79", request="find flights", context=ctx)
        assert not asyncio.run(dispatch_confirm.unlicensed_gate(task, "79", "find flights", wait_s=0.0)), ctx
    assert "79" not in dispatch._PENDING_CONFIRM


def test_the_worker_door_calls_the_gate():
    """Wiring: the gate exists for every worker only if `_run_session` — the one door — asks it."""
    import inspect
    from nucleo.dispatch import session as dispatch_session
    src = inspect.getsource(dispatch_session._run_session)
    assert "unlicensed_gate(task, key, req)" in src


def test_the_gate_registers_the_line_before_it_renews_the_window():
    """Wiring: the line must be registered with the anchor it FOUND, so `open_line` precedes `note_directed` in
    the gate's caller — the other order would make a negative verdict restore the line's own renewal."""
    import inspect
    from voice.engine.llm.providers import attention_turn
    src = inspect.getsource(attention_turn.judge)
    reg, renew = src.find("attention.open_line(verdict"), src.find("attention.note_directed()")
    assert 0 <= reg < renew, "the admitted line is not registered before the window is renewed"
