"""An errand's end state follows the turn's own END verdict and never outlives the errand (T-19 R6).

Demo sandbox at build 86, INIT: «Remember these… even when they are not shown on the calendar». The brief answered END
«none», but the errand's birth re-inferred an end state from his WORDS (`agenda.tasks[title~=…]`), and when the
worker ended `unverifiable` the spec stayed STARTED: the pulse re-read it every 5 s for the whole pass (❌ on every
step) and the delivery said «done, unverified». The class has two halves: (a) a sure END «none» declares that the
order leaves no widget state true, so nothing is inferred; (b) every ending closes the entry, and no spec is
opened for a record that has already ended.
"""
import asyncio
from types import SimpleNamespace

import pytest

from nucleo import circuit
from nucleo.circuit import spec as _spec
from nucleo.circuit import verify as _verify

AGENDA = {"all": [{"widget": "agenda", "collection": "tasks", "where": {"title~": "insurance renewal"}}]}
REMEMBER = ["Remember these: the car insurance renews on March 12, even when it is not shown on the calendar",
            "Recuerda esto: el seguro del coche se renueva el 12 de marzo, aunque no salga en el calendario"]


def _rec(goal, **kw):
    base = dict(uid="T-r6", task_id="r6", goal=goal, status="running", trace_id="", done_when={}, session=None,
                injects=[], kind="generic", relay_gen=0, goal_retried=False, sheet="", surface="voz",
                result_summary="", handoff="", ok=True)
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.fixture
def ledger(monkeypatch):
    inferred = []

    async def infer(goal, **k):
        inferred.append(goal)
        return AGENDA
    async def tell(rec, e, **k):
        return None
    monkeypatch.setattr(_spec, "infer", infer)
    monkeypatch.setattr(_spec, "_tell_worker", tell)
    monkeypatch.setattr(_spec, "persist", lambda *a, **k: None)
    monkeypatch.setattr(_spec, "of_task", lambda *a, **k: None)
    _spec.reset()
    yield inferred
    _spec.reset()


def _born(rec, ctx):
    async def go():
        _spec.born(rec, ctx)
        await asyncio.gather(*list(_spec._BG))
    asyncio.run(go())


@pytest.mark.parametrize("goal", REMEMBER)
def test_a_sure_none_from_the_turn_opens_no_spec(ledger, goal):
    _born(_rec(goal), {"src": "voice", _spec.END_KEY: _spec.NO_END_STATE})
    assert ledger == [] and _spec.open_specs() == []


def test_an_order_without_that_verdict_still_gets_its_end_state(ledger):
    _born(_rec("Add «insurance renewal» to my agenda tasks"), {"src": "voice", _spec.END_KEY: ""})
    assert len(ledger) == 1 and [e["target"] for e in _spec.open_specs()] == ["agenda:tasks"]


def test_a_spec_written_after_its_errand_ended_is_never_opened(ledger):
    _born(_rec("Add «insurance renewal» to my agenda tasks", status="done"), {"src": "voice"})
    assert len(ledger) == 1 and _spec.open_specs() == []


def test_the_brief_end_verdict_is_none_only_when_sure(monkeypatch):
    from nucleo.turn import brief as _tb
    answers = {"sure": ("none", {"used": True}), "unsure": ("", {"used": False, "choice": "none"}),
               "card": ("agenda:tasks", {"used": True}), "absent": ("", None)}
    for name, want in (("sure", "none"), ("unsure", ""), ("card", ""), ("absent", "")):
        monkeypatch.setattr(_tb, "read", lambda h, k, fb, _a=answers[name], **kw: _a)
        assert _spec.end_state_declared({"x": 1}) == want, name
    assert _spec.end_state_declared(None) == ""


@pytest.mark.parametrize("reading", [False, None])     # an inferred unmet reads unverifiable; an unreadable one too
def test_every_ending_closes_the_entry_its_errand_opened(ledger, monkeypatch, reading):
    rec = _rec(REMEMBER[0], done_when=AGENDA)
    e = _spec.open(AGENDA, text=rec.goal, source="worker+inferred", task_id=rec.uid)
    monkeypatch.setattr(_verify, "check", lambda dw, now=None: reading)
    monkeypatch.setattr(_verify, "missing", lambda dw, now=None: ["no row"])
    assert circuit.close(rec, relay_cap=2) == "unverifiable"
    assert e["status"] == "unverifiable" and _spec.open_specs() == []
    assert circuit.tick(now=e["born"] + 60) == []          # nothing left for the pulse to re-read


def test_the_turn_hands_its_end_verdict_to_the_errand_it_commissions():
    """The wiring: without this key in the escalate context, half (a) is a reader nobody writes."""
    import inspect

    from voice.engine.llm.providers import turn_after
    assert "_spec_mod.END_KEY: _spec_mod.end_state_declared(_brief)" in inspect.getsource(turn_after)
