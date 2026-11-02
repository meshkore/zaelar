"""A card on screen shows the turn its declared payload FIELDS (node 12.838, V2-838 R3).

search-buy-used-car ES (2026-11-02): «evita Flexicar» reached the sheet as a `criteria.changes` sentence in the
model's words. The `criteria` op was composed by the voice turn itself (an inline action), and the voice prompt
carries action NAMES only: the declared `excluded` field — the one thing that rules rows out by name — existed in
the manifest and nowhere the composing model looked. A field the model never sees is a field it never fills.

The mechanism is the declared field, not a sentence about behaviour: for a card ON SCREEN the catalog adds one line
with the payload keys of each offered action whose manifest declares a field contract (`how`) — any card. A card
that is not on screen costs nothing, an internal op is not named, and the keys never join an action's name.
"""
from __future__ import annotations

import json
from pathlib import Path

from widgets import brief

ROOT = Path(__file__).resolve().parents[4]


def _fields_line(text: str, wid: str) -> str:
    return next((ln for ln in text.splitlines() if ln.startswith(f"  [{wid}] ") and ": " in ln
                 and ln.split("] ", 1)[1].startswith("campos")), "")


def test_the_sheet_on_screen_shows_the_turn_its_exclusion_field():
    line = _fields_line(brief.for_prompt(open_ids=["results"]), "results")
    assert "criteria: " in line and "excluded" in line.split("criteria: ", 1)[1].split(" ; ")[0]


def test_another_card_on_screen_shows_its_own_declared_fields():
    acts = json.loads((ROOT / "widgets" / "agenda" / "manifest.json").read_text(encoding="utf-8"))["actions"]
    name, spec = next((n, s) for n, s in acts.items() if isinstance(s, dict) and isinstance(s.get("payload"), dict)
                      and s["payload"] and s.get("how") and not s.get("internal"))
    line = _fields_line(brief.for_prompt(open_ids=["agenda"]), "agenda")
    assert f"{name}: {'·'.join(spec['payload'])}" in line


def test_a_card_off_screen_costs_nothing_and_no_key_joins_a_name():
    text = brief.for_prompt(open_ids=[], recent_ids=["results"])
    assert not _fields_line(text, "results"), "payload fields paid for a card that is not on screen"
    row = next(ln for ln in brief.for_prompt(open_ids=["results"]).splitlines() if ln.startswith("- results "))
    assert "excluded" not in row, "a key read as part of an action's name"


def test_only_an_action_that_declares_a_field_contract_is_listed():
    """An internal op is never named; an action whose manifest declares no `how` costs nothing on every turn."""
    acts = {"seen": {"payload": {"x": 1}, "how": "…", "internal": True}, "play": {"payload": {"q": "…", "at": 0}},
            "add": {"payload": {"title": "…", "when": "…"}, "how": "`when` is…"}}
    assert brief._payload_keys(acts) == "add: title·when"
