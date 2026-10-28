"""The tool catalogue is a dict: every tool the model is offered has ONE door, and every door is a tool (refactor2710-05).

`_on_tool_call` was a chain of 32 `elif name == …` arms; a tool declared in the schema with no arm was offered and
silently did nothing, and an arm whose schema was dropped was dead code nobody noticed. Now `acts.tools.CATALOG` is
built from the arm functions themselves (their names are the tool names, written once), `router.tools` offers only
what has a door, and `_on_tool_call` runs a call through the door its name selects.
"""
from __future__ import annotations

from types import SimpleNamespace

from nucleo.acts import tools
from nucleo.flash import router
from nucleo.flash.router_catalog import TOOLS

#: The escape hatch of progressive tool selection: it is a door (it marks a family to recompose), not a schema.
_HATCH = "need_capability"


def _declared() -> set:
    return {t["function"]["name"] for t in TOOLS}


def test_every_declared_tool_has_its_door_and_every_door_a_tool():
    assert _declared() - set(tools.CATALOG) == set(), "a tool offered to the model that nothing runs"
    assert set(tools.CATALOG) - _declared() == {_HATCH}, "a door no schema offers"


def test_the_catalogue_names_each_door_by_its_function():
    assert all(f.__name__ == name for name, f in tools.CATALOG.items())


def test_what_is_offered_is_what_has_a_door(monkeypatch):
    offered = {t["function"]["name"] for t in router.tools()}
    assert offered == _declared()
    monkeypatch.delitem(tools.CATALOG, "recall")
    assert "recall" not in {t["function"]["name"] for t in router.tools()}, "a tool without a door is offered"
    assert "recall" not in {t["function"]["name"] for t in router.tools({"has_widgets": True})}


def test_a_call_runs_through_the_door_its_name_selects(monkeypatch):
    from nucleo.flash import tool_executor_calls as calls
    ran = []
    monkeypatch.setitem(tools.CATALOG, "recall", lambda args, c: ran.append((args, c.text)))
    kw = {k: None for k in calls._on_tool_call.__code__.co_varnames[2:calls._on_tool_call.__code__.co_argcount
                                                                       + calls._on_tool_call.__code__.co_kwonlyargcount]}
    kw.update(self=SimpleNamespace(_superseded=lambda: False), brain=SimpleNamespace(_turn_tools=set(), _turn_calls=[]),
              emit=lambda *a, **k: None, text="¿dónde vivo?")
    calls._on_tool_call("recall", {"query": "dónde vivo"}, **kw)
    assert ran == [({"query": "dónde vivo"}, "¿dónde vivo?")]
