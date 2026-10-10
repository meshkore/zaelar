"""V2-781 — «remove the second one» sent `items: "2"` and the door said nobody named a target.

Measured in `la-cola-de-video-con-palabras-imprecisas` (ES and EN, 2026-10-10): the model called
`youtube.remove {items: "2"}` — exactly the plural form the manifest declares beside `item` («VARIOS con
items="4,5,6"», V2-756) — and the selector guard refused it with «I couldn't tell which one to remove, so I
left everything as it is», because it only looked at `item`. Two turns of «which one?» over an order that
had named its row.

The selector of a destructive action is satisfied by its declared plural sibling (`item` → `items`), the
same way the widget itself reads it. An empty plural still names nothing and is still refused.
"""
from __future__ import annotations

from widgets import contract


def test_the_plural_sibling_names_the_target():
    assert contract.guard("youtube", "remove", {"items": "2"}) is None
    assert contract.guard("youtube", "remove", {"items": "4,5,6"}) is None


def test_the_singular_still_works():
    assert contract.guard("youtube", "remove", {"item": "2"}) is None


def test_nothing_named_is_still_refused():
    for pl in ({}, {"items": ""}, {"items": "  "}):
        r = contract.guard("youtube", "remove", pl)
        assert r and r.get("error") == contract.SELECTOR_MISSING


def test_an_undeclared_plural_does_not_open_the_door():
    """Only a sibling the action DECLARES counts — `agenda.cancel_meeting` declares no `titles`."""
    r = contract.guard("agenda", "cancel_meeting", {"titles": "Dentist"})
    assert r and r.get("error") == contract.SELECTOR_MISSING
