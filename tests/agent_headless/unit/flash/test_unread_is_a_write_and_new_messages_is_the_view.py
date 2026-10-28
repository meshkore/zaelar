"""`unread` is a WRITE in his real app; «do I have new messages?» belongs to `show_view` (refactor2710-99, CRIT-K7).

«Do I have any new WhatsApp messages?» → the model called `mensajeria:unread`, the WRITE that marks a message unread in
his real app, and the card never opened; in Spanish it chose `show_view`. `unread`'s descriptor began «Deja SIN LEER…»
and said nothing of what it is NOT, so «new / unread messages» read as its own words.

A descriptor is written under the cut (`MAX_DESC_CHARS`) and measured against its NEIGHBOUR: `unread` says it WRITES
and names the homograph it is not; `show_view` carries the question in both languages among its own examples.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from nucleo.turn import brief as _tb

_ENGINE = pathlib.Path(__file__).resolve().parents[4]


def _cut(action: str) -> str:
    acts = json.loads((_ENGINE / "widgets/mensajeria/manifest.json").read_text(encoding="utf-8"))["actions"]
    return acts[action]["desc"][:_tb.MAX_DESC_CHARS]


def test_unread_says_it_writes_and_names_what_it_is_not():
    cut = _cut("unread")
    assert "ESCRIBE" in cut and "app real" in cut, cut
    assert "«mark it unread»" in cut and "«déjalo como no leído»" in cut, "its own order, in both languages"
    head, _, tail = cut.partition("NO contesta")
    assert tail and "show_view" in tail and "nuevos" in tail, "the homograph is named, and where it goes"
    assert "nuevo" not in head.lower() and "new" not in head.lower(), "«new» is never one of its own words"


@pytest.mark.parametrize("question", ["«¿tengo whatsapps nuevos?»", "«do I have new WhatsApp messages?»"])
def test_the_new_messages_question_is_one_of_the_views_own_examples(question):
    assert question in _cut("show_view"), _cut("show_view")


def test_the_view_still_names_its_payload_under_the_cut():
    cut = _cut("show_view")
    assert "platform" in cut and "window_h" in cut, cut
