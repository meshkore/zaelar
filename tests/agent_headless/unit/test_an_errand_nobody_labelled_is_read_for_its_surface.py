"""An errand that arrives with NO declared surface takes the turn brief's reading of it (demo A1, 2026-09-28).

«Johnny, find me three 27-inch 4K monitors under 400 dollars — show me when you have them.» escalated without a
surface; the kind was `generic`, whose fallback is «voice», so no sheet opened. The operator watched an empty
screen, «Minimise that» had nothing to minimise, and the results turned up minutes later over a playing video.
The brief (one trip at turn start, nothing blocks) now also asks what he will look at; the escalation uses it
only when the model declared nothing, and an unsure reading leaves today's fallback.
"""
import inspect
import threading

from nucleo import surfaces
from nucleo.flash import turn_brief as _tb


def _brief(choice, conf):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t", "open_ids": [],
            "result": {surfaces.SURFACE_KEY: {"choice": choice, "confidence": conf}}}


def test_the_brief_asks_it():
    qs = _tb.build("find me three 27-inch 4K monitors under 400 dollars")
    assert surfaces.SURFACE_KEY in qs and surfaces.LIST in qs[surfaces.SURFACE_KEY]["criteria"]


def test_a_sure_reading_names_the_surface():
    s = surfaces.from_brief(_brief("lista", 0.93))
    assert s == surfaces.LIST and surfaces.opens_sheet(s)


def test_an_unsure_or_absent_reading_leaves_the_fallback():
    assert surfaces.from_brief(_brief("lista", 0.5)) == ""
    assert surfaces.from_brief(None) == ""
    assert surfaces.from_brief(_brief("carousel", 0.99)) == ""


def test_the_escalation_uses_it_only_when_the_model_declared_none():
    from voice.engine.llm.providers import nucleo as prov
    src = inspect.getsource(prov)
    i = src.index("or _surfaces_mod.from_brief(_brief)")
    assert 'escalate_req["surface"].get(req, "")' in src[i - 120:i], "the model's own declaration comes first"
