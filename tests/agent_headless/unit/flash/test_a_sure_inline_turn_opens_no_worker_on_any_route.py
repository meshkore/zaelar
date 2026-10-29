"""A SURE `handle_inline` opens no worker on ANY route of the turn (T-19 R6c), and the reader is the single door.

Demo pass 7, INIT: «Remember these future responsibilities even when they are not currently displayed on the
calendar…» — brief `order` 0.78 · catalogue `agenda` 0.93 · `handle_inline` 0.96, END not asked (no card open). The
model replied «Already kept…» and called nothing; the order-over-a-card lane escalated it anyway, and a worker wrote
«Tesla/Ducati insurance renewal» meetings. `promise_backstop` and the word tables already honoured a sure inline;
this lane did not. Now every forced escalation asks ONE reader, `escalation_guard.keeps_it_inline`.
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import threading
import types
from pathlib import Path

import pytest

from nucleo.flash import escalation_guard as EG
from nucleo.turn import brief as tb

ENGINE = Path(__file__).resolve().parents[4]
REMEMBER = {"en": "Remember these future responsibilities even when they are not currently displayed on the "
                  "calendar: car insurance renewal on March 12, 2027; registration renewal in May 2027.",
            "es": "Recuerda estas responsabilidades aunque ahora no salgan en el calendario: la renovación del "
                  "seguro del coche el 12 de marzo de 2027 y la de la matrícula en mayo de 2027."}
REPLY = {"en": "Already kept — car insurance March 12th 2027, registration in May 2027.",
         "es": "Ya lo tengo guardado: el seguro el 12 de marzo de 2027 y la matrícula en mayo."}


def _brief(escalate: tuple, *, order=0.78, card="agenda") -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "result": {
        tb.ESCALATE_KEY: {"choice": escalate[0], "confidence": escalate[1]},
        tb.REQUEST_KEY: {"choice": "order", "confidence": order},
        tb.CATALOG_KEY: {"choice": card, "confidence": 0.93},
        tb.WORDS_KEY: {"choice": "act", "confidence": 0.84}}}


@pytest.fixture(autouse=True)
def _no_repair(monkeypatch):
    from nucleo.flash import act_repair
    monkeypatch.setattr(act_repair, "call_for_promise_or_order", lambda *a, **k: None)


def _voice_lane(monkeypatch, brief, said, reply, *, acted=None, data_done=False):
    """The real post-stream lanes of the voice turn, its state stubbed; the root conftest isolates every store."""
    from nucleo.flash import post_stream as P, post_stream_lanes as L, router

    async def _untouched(no_tool, *a, **k):
        return no_tool
    monkeypatch.setattr(P._resume_turn, "before_backstops", _untouched)
    events: list = []
    escalate_req = {"v": None}
    kw = {n: None for n in inspect.signature(L.run_the_light_lanes).parameters}
    kw.update(_brief=brief, _op_text=said, operator_text=said, text=said, spoken_text=reply, spoken=reply,
              _no_tool=not (acted or data_done), _router=router, emit=lambda *a, **k: events.append(a),
              escalate_req=escalate_req, music_req={"v": None}, acted=dict(acted or {}), data_done={"v": data_done},
              clarify={}, _tool_fired=set(), _shown_ids=set(),
              brain=types.SimpleNamespace(_window=[], _last_spoken=""), _named_by_verdict="",
              _identify=lambda t: "", _identify_system=lambda t: None, with_also_named=lambda ids, t: ids,
              **{k: {"v": None} for k in ("read_req", "recall_req", "reopen_req", "reveal_req", "search_req",
                                          "listing_req", "images_req")})
    asyncio.run(L.run_the_light_lanes(**kw))
    return escalate_req, events


@pytest.mark.parametrize("lang", ["en", "es"])
def test_a_remember_order_kept_inline_opens_no_worker(monkeypatch, lang):
    req, events = _voice_lane(monkeypatch, _brief(("handle_inline", 0.96)), REMEMBER[lang], REPLY[lang])
    assert req["v"] is None, req
    assert any("ANULADA" in str(e[1]) for e in events if len(e) > 1)


@pytest.mark.parametrize("lang", ["en", "es"])
def test_the_same_order_with_an_unsure_verdict_keeps_todays_path(monkeypatch, lang):
    """V2-773 F1's case stays: an order the catalogue addressed, nothing called, escalation unsure → the work is owed."""
    req, _ = _voice_lane(monkeypatch, _brief(("handle_inline", 0.15)), REMEMBER[lang], REPLY[lang])
    assert req["v"] == REMEMBER[lang]


@pytest.mark.parametrize("said", ["Book it and research the flights to Lisbon for next week",
                                  "Resérvalo e investiga los vuelos a Lisboa para la semana que viene"], ids=["en", "es"])
def test_a_sure_escalation_still_escalates(monkeypatch, said):
    req, _ = _voice_lane(monkeypatch, _brief(("escalate", 0.95), order=0.95, card="none"), said, "On it.")
    assert req["v"] == said


@pytest.mark.parametrize("lang", ["en", "es"])
def test_a_turn_whose_inline_pass_acted_owes_no_worker(monkeypatch, lang):
    for b in (_brief(("handle_inline", 0.96)), _brief(("handle_inline", 0.15))):
        req, _ = _voice_lane(monkeypatch, b, REMEMBER[lang], REPLY[lang], data_done=True)
        assert req["v"] is None


def test_the_promise_backstop_asks_the_same_reader(monkeypatch):
    from voice.engine.llm.providers import promise_backstop as PB
    from nucleo.flash import router
    monkeypatch.setattr(router, "looks_like_web_task", lambda t: True)
    started = []
    out = PB.run("I'll get it done", did_act=False, op_text=REMEMBER["en"], prev_pending=[], emit=lambda *a, **k: None,
                 escalate=lambda t, **k: started.append(t), similar_pending=lambda *a: False,
                 brief=_brief(("handle_inline", 0.96)))
    assert out == "" and started == []


# ── the single door: a forced escalation that does not ask the reader goes red ────────────────────────────────

#: Every module where the TURN (not the model's own tool call) forces an escalation. Still outside, recorded as open
#: work: `post_stream_acts`' marketplace / modify-widget guard (V2-057), which reads the words without the brief.
FORCED = ("nucleo/flash/post_stream_lanes.py", "voice/engine/llm/providers/promise_backstop.py")
READERS = {"keeps_it_inline", "word_tables"}
#: A sink that does not ask, with why — and nothing else.
EXEMPT = {("nucleo/flash/post_stream_lanes.py", "reopen"): "he asked to bring back a finished errand (task_recall)"}


def _sinks(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name) and t.value.id == "escalate_req"
                for t in node.targets) and not (isinstance(node.value, ast.Constant) and node.value.value is None):
            yield node
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "escalate":
            yield node


def _asks(expr) -> bool:
    return any(isinstance(n, ast.Call) and getattr(n.func, "attr", getattr(n.func, "id", "")) in READERS
               for n in ast.walk(expr))


def _guarded(fn, sink) -> bool:
    """The reader decides THIS sink: it is in the test of an `if` the sink sits under, or an earlier sibling
    `if <reader>: return` stands between the block's start and the sink. A reader called elsewhere does not count."""
    def walk(stmts, ancestors_ok: bool) -> bool | None:
        early_exit = False
        for st in stmts:
            if any(n is sink for n in ast.walk(st)):
                if st is sink or isinstance(st, ast.Expr) and st.value is sink:
                    return ancestors_ok or early_exit
                if isinstance(st, ast.If):
                    in_body = any(any(n is sink for n in ast.walk(b)) for b in st.body)
                    ok = ancestors_ok or early_exit or (_asks(st.test) and in_body)
                    got = walk(st.body if in_body else st.orelse, ok)
                    return got if got is not None else ok
                for field in ("body", "orelse", "handlers", "finalbody"):
                    blk = getattr(st, field, None) or []
                    blk = [h for h in blk] if field != "handlers" else [x for h in blk for x in h.body]
                    got = walk(blk, ancestors_ok or early_exit)
                    if got is not None:
                        return got
                return ancestors_ok or early_exit
            if isinstance(st, ast.If) and _asks(st.test) and any(isinstance(x, ast.Return) for x in st.body):
                early_exit = True
        return None
    return bool(walk(fn.body, False))


def unguarded(sources: dict[str, str]) -> list[str]:
    out = []
    for rel, src in sources.items():
        tree = ast.parse(src)
        for fn in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            for s in _sinks(fn):
                seg = ast.get_source_segment(src, s) or ""
                if any(rel == r and key in seg for r, key in EXEMPT):
                    continue
                if not _guarded(fn, s):
                    out.append(f"{rel}:{s.lineno}")
    return sorted(set(out))


def _sources():
    return {rel: (ENGINE / rel).read_text() for rel in FORCED}


def test_every_forced_escalation_asks_the_one_reader():
    assert unguarded(_sources()) == []


def test_the_guard_sees_a_route_that_skips_the_reader():
    src = _sources()
    bad = src["nucleo/flash/post_stream_lanes.py"] + (
        "\n\nasync def _a_new_route(escalate_req, _op_text, _brief, emit):\n    _eg.keeps_it_inline(_brief)\n"
        "    if _op_text:\n        escalate_req['v'] = _op_text\n")
    assert unguarded({**src, "nucleo/flash/post_stream_lanes.py": bad}), "a new unguarded route must go red"
