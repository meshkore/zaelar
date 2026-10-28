"""An errand the model sent without a `done_when` is born with the end state the brief already read (refactor2710-06 T-03).

The brief's END verdict is paid for in the turn; rendered from the template a card on screen declares, it is the errand's
spec. No sure verdict, or no card declaring that target → None, and the spec infers it once as before.
"""
from __future__ import annotations

import threading

import pytest

from nucleo.acts import errand
from nucleo.circuit import spec

_CARD = {"actions": {"add": {"desc": "adds an item", "done_when": {"widget": "notes", "collection": "items"}},
                     "show": {"desc": "a view"}}}


def _brief(choice: str | None, conf: float = 0.95) -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-end", "open_ids": ["notes"],
            "result": ({spec.END_KEY: {"choice": choice, "confidence": conf}} if choice else {})}


@pytest.fixture(autouse=True)
def _card(monkeypatch):
    monkeypatch.setattr(spec, "_manifest", lambda wid: _CARD if str(wid).split("::")[0] == "notes" else {})
    monkeypatch.setattr(spec, "_snapshot", lambda dw: None)


def test_a_sure_end_verdict_becomes_the_errands_spec():
    dw = errand.done_when_from_brief(_brief("notes:items"))
    assert dw and spec.target_of(dw) == "notes:items"


def test_no_verdict_an_unsure_one_or_an_undeclared_target_gives_none():
    assert errand.done_when_from_brief(_brief(None)) is None
    assert errand.done_when_from_brief(_brief("notes:items", 0.3)) is None
    assert errand.done_when_from_brief(_brief("agenda:meetings")) is None, "no card on screen declares it"
    assert errand.done_when_from_brief(None) is None
