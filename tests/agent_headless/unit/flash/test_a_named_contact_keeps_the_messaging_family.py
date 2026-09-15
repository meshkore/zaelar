"""V2-705 (Nivel 2) · A request that NAMES a contact keeps the messaging tools in the catalog — from STATE.

Measured 2026-09-15 (session 878b0122). «Write to my contact Kryptonite, which is in the contacts database,
and organise a meeting for tomorrow» reached the model with `messaging` and `widgets` TRIMMED — «write»,
«contact», «meeting» are not seed words — so `send_to` was absent and the only door was a Brain Worker,
which spent six minutes and sent zero messages. V2-682 had patched the identical failure with seeds and a
carried window three days earlier; it recurred because the fix read WORDS, and the words change every
session. The one durable fact of «write to X» is X — a name that resolves in the operator's own directory.

`nucleo/flash/addressed.py` reads that name through the same `directory.resolve` the send door uses, and
the selector forces `messaging` (and, by implication, `widgets`) when it resolves. These cases pin: the
name is found however the sentence is phrased, a plain turn is left trimmed, an unknown name forces
nothing, and the rail is STATE (a directory read) not a verb table.
"""
from __future__ import annotations

import re

import pytest


@pytest.fixture
def directory_with_kryptonite(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.contactos import data as cd
    cd.apply_action("add_contact", {"name": "Cryptonite", "kind": "person", "group": "work",
                                    "channels": [{"platform": "telegram", "handle": "@cryptonite_fund"}],
                                    "preferred": "telegram"})
    return cd


# ── addressed.py: the reader ────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "write to my contact Kryptonite and organise a meeting for tomorrow",
    "Kryptonite, which is in the contacts database, needs a message",
    'escríbele a "Cryptonite" y concierta una videollamada',
    "send Cryptonite the meeting link",
])
def test_a_named_contact_is_found_however_the_sentence_is_phrased(directory_with_kryptonite, text):
    from nucleo.flash import addressed
    assert addressed.contact_in(text).lower().startswith("cryptonite")


def test_a_turn_that_names_nobody_resolves_to_nothing(directory_with_kryptonite):
    from nucleo.flash import addressed
    assert addressed.contact_in("what's the weather in Madrid tomorrow") == ""
    assert addressed.contact_in("remove the appointment tomorrow at seven") == ""


def test_an_unknown_name_forces_nothing(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from nucleo.flash import addressed
    assert addressed.contact_in("write to Napoleon Bonaparte") == ""


def test_an_unreadable_directory_is_not_a_crash(monkeypatch):
    from nucleo.flash import addressed
    import widgets.directory as directory
    monkeypatch.setattr(directory, "resolve", lambda name: (_ for _ in ()).throw(RuntimeError("boom")))
    assert addressed.contact_in("write to Kryptonite") == ""


# ── the selector: the wiring ────────────────────────────────────────────────────────────────────────────

def _select(turn_text):
    from nucleo.flash import router, tool_selection as tsel
    tools = router.tools(router.tool_context())
    return tsel.select_for_turn(tools, turn_text=turn_text, window=None)


def test_the_measured_turn_keeps_messaging_and_the_widget_door(directory_with_kryptonite):
    out, rep = _select("write to my contact Kryptonite and organise a meeting for tomorrow")
    assert "messaging" in rep["kept"], rep
    assert "widgets" in rep["kept"], "messaging IMPLIES widgets — send_to's read door lives there (V2-645)"
    names = {(t.get("function") or {}).get("name") for t in out}
    assert "widget_data" in names, "the tool that carries send_to must be in the catalog"


def test_a_turn_with_no_contact_still_trims_messaging(directory_with_kryptonite):
    _, rep = _select("play some jazz")
    assert "messaging" in rep["omitted"], "the rail only adds families, it never keeps them for nothing"


def test_the_contact_forces_the_family_even_from_a_carried_fragment(directory_with_kryptonite):
    """The request is routinely spread over turns: the name may sit in a previous fragment, and the closing
    sentence («do this») names nothing. The carried window feeds the same reader."""
    from nucleo.flash import router, tool_selection as tsel
    tools = router.tools(router.tool_context())
    window = [{"role": "user", "text": "I need you to write to my contact Kryptonite"},
              {"role": "user", "text": "So do this. Right now."}]
    _, rep = tsel.select_for_turn(tools, turn_text="So do this. Right now.", window=window)
    assert "messaging" in rep["kept"], rep


def test_the_rail_is_state_not_a_verb_table():
    """Source-level: the selector consults the DIRECTORY, not a widened `_HINTS`. The seed list stays the
    short one V2-682 deliberately kept — the fix for a recurring miss is not another verb."""
    import pathlib
    src = pathlib.Path(__file__).resolve().parents[4] / "nucleo/flash/tool_selection.py"
    text = src.read_text(encoding="utf-8")
    body = text[text.index("def select_for_turn("):]
    assert "addressed" in body and "contact_in" in body
