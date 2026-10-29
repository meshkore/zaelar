"""The words-after-data pass composes over a SMALL, declared context (V2-831 T-19 R5, demo sandbox build 86, C2).

«find me a free 45 minutes tomorrow afternoon to talk with Rowan, after my last meeting»: `find_free` returned at
1.7 s, then `📖 la data-op DEVOLVIÓ datos y el turno debe palabras` ran its pass for 11 s and the turn closed with
`⏱ turno LENTO 12627 ms — PROMPT GRANDE 19216 tok`. The suspicion was that the pass re-sent the whole turn prompt.
Measured, it does not: the 19 k tokens are the FIRST pass's (the turn's slow verdict reads only `llm_metrics`), and
the pass sends the operator's sentence, the op's answer (capped), the card's own rows for a subset lens (capped) and
the language lock — ~0.7 k tokens for C2. The 11 s were spent before the pass's first token (its SKIP and the turn's
end are 3 ms apart), so the pass now reports its own duration and size on the timeline.

What this freezes, for ANY data op that answers: what the pass sends stays under a ceiling at its WORST case (every
cap full), in o200k tokens, and the answer still carries the op's data. The ceilings only go down.
"""
from __future__ import annotations

import asyncio
import json
import threading

import pytest

# o200k tokens of (system + user) the pass hands `speak`, every cap full. Measured 2026-10-29: 1 409 · 1 868
# (C2 itself sends ~0.7 k), plus a small margin.
CEILINGS = {"agenda:find_free": 1_450, "mensajeria:show_view": 1_950}


def _tokens(text: str) -> int:
    import tiktoken
    return len(tiktoken.get_encoding("o200k_base").encode(text))


def _brief():
    from nucleo.turn import brief as tb
    ev = threading.Event(); ev.set()
    return {"event": ev, "turn_id": "t", "open_ids": [],
            "result": {tb.REQUEST_KEY: {"choice": "order", "confidence": 0.9},
                       tb.WORDS_KEY: {"choice": "tell", "confidence": 0.9}}}


def _find_free_result() -> dict:
    """A real `find_free` answer over a crowded day — the agenda's own computation, not a hand-written shape."""
    from widgets.agenda import free
    ms = [{"title": f"Meeting {i:02d} with the architecture, product and platform teams " * 3, "date": "2026-10-30",
           "startTime": f"{8 + i // 4:02d}:{(i % 4) * 15:02d}", "endTime": f"{8 + i // 4:02d}:{(i % 4) * 15 + 10:02d}"}
          for i in range(24)]     # a crowded morning (the answer's block at its cap) and a free afternoon
    db = {"meetings": ms}
    return free.remember(db, free.find(ms, "2026-10-30", {"date": "2026-10-30", "duration_min": 45}), {})


def _inbox_result() -> dict:
    return {"ok": True, "result": {"chats": [{"name": f"Inworld AI billing {i}", "platform": "email",
                                              "last": "Your invoice for October is ready " * 4} for i in range(80)]}}


CASES = {
    "agenda:find_free": ("find me a free 45 minutes tomorrow afternoon to talk with Rowan, after my last meeting",
                         _find_free_result, "first_fit"),
    "mensajeria:show_view": ("check my email, did inworld send me something?", _inbox_result, "Inworld AI"),
}


def _sent(monkeypatch, case: str) -> dict:
    """Run the ONE op-answer door over the op and return what it handed the pass: system + user + label."""
    from nucleo.flash import post_stream as pst, post_stream_acts as psa
    from nucleo.turn.prompt import builder
    text, make, _ = CASES[case]
    wid, action = case.split(":")
    if wid == "mensajeria":   # a SUBSET lens: the card's own rows for his words ride with it — at their cap
        import widgets.mensajeria.data as md
        monkeypatch.setattr(md, "read_query", lambda q: "Inworld AI <billing@example.com> · invoice · " * 400,
                            raising=False)
    monkeypatch.setattr(pst._direct_action, "on_screen_now", lambda w: True)
    seen: dict = {}

    async def _speak(system, user, cap, label):
        seen.update(system=system, user=user, label=label)

    async def _go():
        fut = asyncio.get_running_loop().create_future()
        fut.set_result(make())
        return await psa.speak_the_ops_answer(
            _brief=_brief(), _op_text=text, _turn_op_tasks=[(wid, fut)], data_done={"ops": [(wid, action)]},
            read_req={"v": None}, escalate_req={"v": None}, search_req={"v": None}, speak=_speak,
            emit=lambda *a, **k: seen.setdefault("emits", []).append((a, k)), _prompt_mod=builder)
    assert asyncio.run(_go()), f"{case}: the door did not speak"
    return seen


@pytest.fixture(autouse=True)
def _english(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")   # the longer language lock (the non-Spanish warning rides it)


@pytest.mark.parametrize("case", list(CASES))
def test_the_pass_sends_a_small_declared_context(monkeypatch, case):
    seen = _sent(monkeypatch, case)
    n = _tokens(seen["system"]) + _tokens(seen["user"])
    assert n <= CEILINGS[case], (
        f"{case}: the words-after-data pass sends {n} o200k tokens (ceiling {CEILINGS[case]}). It composes over his "
        f"sentence and the op's answer, never the turn's prompt: find what grew before raising anything.")


@pytest.mark.parametrize("case", list(CASES))
def test_the_answer_still_carries_the_ops_data(monkeypatch, case):
    seen = _sent(monkeypatch, case)
    _, _, datum = CASES[case]
    assert datum in seen["system"] and seen["label"] == "op answer compose"
    assert CASES[case][0] in seen["system"] and seen["user"] == CASES[case][0]


def test_the_pass_reports_its_own_time_and_size(monkeypatch):
    """The turn's slow verdict only knows the first pass; this pass names itself."""
    seen = _sent(monkeypatch, "agenda:find_free")
    perf = [(a, k) for a, k in seen["emits"] if a and a[0] == "perf"]
    assert perf, "the pass left no measurement of its own"
    extra = perf[-1][1]["extra"]
    assert extra["pass"] == "op answer compose" and isinstance(extra["ms"], int) and 0 < extra["prompt_tokens_est"] < 2_000


def test_disarmed_the_full_turn_prompt_goes_red(monkeypatch):
    """Disarm: the pass composes over the turn's whole system prompt again → the ceiling catches it."""
    from nucleo.flash import widget_read
    real = widget_read.op_answer_system
    turn_prompt = json.dumps({"tools": ["catalogue"] * 4000})        # ≈ the 19 k-token first-pass prompt of C2
    monkeypatch.setattr(widget_read, "op_answer_system", lambda *a, **k: turn_prompt + "\n" + real(*a, **k))
    assert widget_read.op_answer_system is not real
    for case in CASES:
        seen = _sent(monkeypatch, case)
        assert _tokens(seen["system"]) + _tokens(seen["user"]) > CEILINGS[case], f"{case}: the disarm went unseen"
