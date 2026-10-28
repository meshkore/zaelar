"""A bare «Done.» stands only when the cards back it (docs-single-recipe-not-a-list EN, 2026-10-14).

Sandbox 20261014-120418-en: the recipe was owed on the document sheet — an end state re-read every five seconds as
UNMET — and the turn that resolved the build question with a «no» said the canned «Done.» over the empty sheet. The
bare acknowledgement WE are about to say is checked against the end states owed on the cards the turn wrote to, and
against the errands the turn just started (`nucleo/turn/reply_receipts.bare_ack`, refactor2710-03): our own line is
chosen from the facts, never repaired by reading words afterwards.
"""
from __future__ import annotations

import pytest

from i18n import langs
from nucleo.circuit import spec
from nucleo.turn import reply_receipts
from widgets.documento import data as documento

BODY = {"widget": "documento", "field": "body", "expect": "present"}


@pytest.fixture(autouse=True)
def _clean():
    spec.reset()
    documento.apply_action("clear", {})
    yield
    spec.reset()
    documento.apply_action("clear", {})


def _lang():
    return langs.current_language()


def test_done_over_an_empty_sheet_that_is_owed_is_not_said():
    spec.open(BODY, text="give me the carbonara recipe", widget="documento")
    assert reply_receipts.bare_ack(_lang().data_ack, None) == _lang().done_not_on_card


def test_done_over_a_sheet_that_holds_its_body_stands():
    spec.open(BODY, text="give me the carbonara recipe", widget="documento")
    documento.apply_action("show", {"kind": "markdown", "title": "Carbonara", "body": "# Carbonara\n\n- 400 g spaghetti"})
    assert reply_receipts.bare_ack(_lang().data_ack, None) == _lang().data_ack


def test_done_over_an_errand_this_turn_just_started_is_not_said():
    assert reply_receipts.bare_ack(_lang().data_ack, None, beside=True) == _lang().done_just_started


@pytest.mark.parametrize("said", ["ok book it, call it catch up with Rowan", "vale, resérvalo, llámalo ponerme al día con Rowan"])
def test_an_end_state_another_request_left_open_never_unsays_this_turns_ack(said):
    """Demo sandbox 2026-10-28, C2/C3: an INIT «remember» item had inferred three agenda tasks nobody asked for, the
    spec stayed open and unmet all session, and the slot found and the meeting booked were both acked with «It isn't
    on the card yet». With this turn's words, only the end states THIS sentence owes are read."""
    spec.open({"widget": "agenda", "collection": "tasks", "where": {"title~": "Tesla insurance renewal"}},
              text="Remember these future responsibilities even when they are not on the calendar", widget="agenda")
    assert reply_receipts.bare_ack(_lang().data_ack, {"agenda"}) == _lang().done_not_on_card, "without his words: as before"
    assert reply_receipts.bare_ack(_lang().data_ack, {"agenda"}, said=said) == _lang().data_ack
    spec.open(BODY, text=said, widget="documento")
    assert reply_receipts.bare_ack(_lang().data_ack, {"documento"}, said=said) == _lang().done_not_on_card, "its own stays"


def test_a_write_on_another_card_is_judged_by_that_card_only():
    spec.open(BODY, text="give me the carbonara recipe", widget="documento")
    assert reply_receipts.bare_ack(_lang().data_ack, {"agenda"}) == _lang().data_ack
    assert reply_receipts.bare_ack(_lang().data_ack, {"documento"}) == _lang().done_not_on_card
