"""Node 3.60 — Jev route pre-choice forces families; anything unsure keeps today's path.

Contract under test (`nucleo/flash/tool_selection.py`, T-jev-router): a confident Jev route
verdict UNIONs families into the retrieval force set (never removes — state gates already ran);
high-confidence pure chat in a quiet state offers no tools at all (the kickoff precedent);
anything unsure, off, `other` or `escalate` resolves to empty force, and the offered catalog is
then bit-identical to the no-Jev path. No tool is added, renamed or regated here, so the
`test_router.py` catalog contract holds untouched.
"""
import json
import threading

import pytest

from nucleo import jev
from nucleo.flash import router as _router
from nucleo.flash import tool_selection as tsel


def _handle(choice, confidence=0.9):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "result": {"choice": choice, "confidence": confidence,
                                   "probs": {choice: confidence}, "latency_ms": 120}}


def _unsure_handle(choice="show", confidence=0.2):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "result": {"choice": choice, "confidence": confidence,
                                   "probs": {choice: confidence}, "latency_ms": 60}}


def _names(tools):
    return [t.get("function", {}).get("name", "") for t in tools]


def test_the_route_catalog_offers_exactly_the_six_declared_kinds():
    """The candidate set is fixed and reviewable: five routes + `other`. A seventh kind means the
    contract changed and the auditor was not told."""
    assert list(tsel.ROUTE_KINDS) == ["chat", "search", "show", "widget_data", "escalate", "other"]


def test_a_confident_show_forces_widgets_retrieval_misses(monkeypatch):
    """The behavior this wiring adds: «display that thing» names no seed word, so retrieval trims
    the widgets family away; a confident Jev show verdict forces it back. Removing the force union
    turns this red.

    ⚠️ V2-726 F0 turned trimming OFF by default (it costs 35% more — see `tool_selection.enabled`),
    so there is no longer a retrieval miss to rescue on the shipped path: this case now describes
    the mechanism with the trim switched on, and the route pre-choice itself is dead code pending
    V2-726 §3.1. Kept rather than deleted because the union rule is what a future trim would reuse."""
    monkeypatch.setenv("ZAELAR_TOOL_SELECTION", "1")
    tools = _router.tools(None)
    text = "display that thing"
    bare, _ = tsel.select(tools, turn_text=text)
    assert "show_widget" not in _names(bare)  # the retrieval miss this rescues
    force, bare_chat = tsel.resolve_route(_handle("show"))
    assert (force, bare_chat) == ({"widgets"}, False)
    forced, _ = tsel.select(tools, turn_text=text, force=force)
    assert "show_widget" in _names(forced)


def test_a_confident_search_forces_web_and_widget_data_forces_widgets():
    force, bare_chat = tsel.resolve_route(_handle("search"))
    assert (force, bare_chat) == ({"web"}, False)
    force, bare_chat = tsel.resolve_route(_handle("widget_data"))
    assert (force, bare_chat) == ({"widgets"}, False)


def test_escalate_and_other_change_nothing():
    """A confident `escalate` keeps the current path (commissioning a worker is T-jev-escalate's
    job, not this one's); `other` — music, video, messages, memory — keeps it too."""
    assert tsel.resolve_route(_handle("escalate")) == (set(), False)
    assert tsel.resolve_route(_handle("other")) == (set(), False)


def test_an_unsure_verdict_or_a_missing_handle_keeps_todays_path():
    assert tsel.resolve_route(_unsure_handle()) == (set(), False)
    assert tsel.resolve_route(None) == (set(), False)


def test_empty_force_is_bit_identical_to_no_jev():
    """The off-parity proof the task demands: with an empty force the offered catalog serializes
    byte-for-byte like the no-Jev call, so an unsure turn cannot shift the prompt."""
    tools = _router.tools(None)
    without, _ = tsel.select(tools, turn_text="display that thing")
    with_jev, _ = tsel.select(tools, turn_text="display that thing", force=set())
    assert json.dumps(with_jev, ensure_ascii=False) == json.dumps(without, ensure_ascii=False)


def test_confident_chat_in_a_quiet_state_offers_no_tools():
    """Pure conversation needs no schemas: ~22 KB of tools is pure noise. The kickoff already does
    exactly this (`_turn_tools = []`), so the shape is precedented."""
    assert tsel.resolve_route(_handle("chat", 0.9), quiet_state=True) == (set(), True)


def test_chat_keeps_every_tool_when_something_is_pending():
    """Removal needs stronger evidence than addition AND a quiet state: with a worker asking, a
    confirm pending, or anything of the sort, the model keeps every tool it may need."""
    assert tsel.resolve_route(_handle("chat", 0.95), quiet_state=False) == (set(), False)
    assert tsel.resolve_route(_handle("chat", 0.6), quiet_state=True) == (set(), False)


def test_a_disabled_jev_never_fires_and_never_forces(monkeypatch):
    """`ZAELAR_JEV=0` restores the pre-change behavior exactly: no ask, no force, no bare chat."""
    monkeypatch.setattr(jev, "_read_key", lambda: "k")
    monkeypatch.setenv("ZAELAR_JEV", "0")
    assert tsel.ask_route_async("hola, ¿qué tal?") is None
    assert tsel.resolve_route(None) == (set(), False)


def test_no_tool_is_added_renamed_or_regated_by_this_change():
    """The `test_router.py` catalog contract still holds: the route pre-choice trims the OFFER,
    never the catalog."""
    assert not [t for t in _router.TOOLS
                if "route" in (t.get("function", {}).get("name", ""))]
    assert set(tsel.FAMILIES) == {"core", "widgets", "workers", "cluster",
                                  "messaging", "media", "web", "memory"}
