"""A bare «Done.» stands only when the cards back it (docs-single-recipe-not-a-list EN, 2026-10-14).

Sandbox 20261014-120418-en: the recipe was owed on the document sheet — an end state re-read every five seconds as
UNMET — and the turn that resolved the build question with a «no» said the canned «Done.» over the empty sheet. On a
turn that wrote to a card or answered a confirmation, «Done.» is checked against the end states owed on those cards
and against the errands the turn just started; a reply with content of its own is never touched.
"""
from __future__ import annotations

import pytest

from i18n import langs
from nucleo import spec
from nucleo.flash import done_backing
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
    assert done_backing.backed(_lang().data_ack, "confirm_task_no", {}) == _lang().done_not_on_card


def test_done_over_a_sheet_that_holds_its_body_stands():
    spec.open(BODY, text="give me the carbonara recipe", widget="documento")
    documento.apply_action("show", {"kind": "markdown", "title": "Carbonara", "body": "# Carbonara\n\n- 400 g spaghetti"})
    assert done_backing.backed(_lang().data_ack, "confirm_task_no", {}) == _lang().data_ack


def test_done_over_an_errand_this_turn_just_started_is_not_said():
    assert done_backing.backed(_lang().data_ack, "confirm_task_no", {"beside": ["7"]}) == _lang().done_just_started


def test_a_write_on_another_card_is_judged_by_that_card_only():
    spec.open(BODY, text="give me the carbonara recipe", widget="documento")
    extra = {"executed": "widget_data", "ops": [{"widget": "agenda", "act": "add_meeting"}]}
    assert done_backing.backed(_lang().data_ack, "widget_data", extra) == _lang().data_ack
    extra = {"executed": "widget_data", "ops": [{"widget": "documento", "act": "show"}]}
    assert done_backing.backed(_lang().data_ack, "widget_data", extra) == _lang().done_not_on_card


def test_a_reply_with_content_of_its_own_is_left_alone():
    spec.open(BODY, text="give me the carbonara recipe", widget="documento")
    said = "Here it is — the classic Roman carbonara."
    assert done_backing.backed(said, "confirm_task_no", {}) == said
    assert done_backing.backed(_lang().data_ack, "chat", {}) == _lang().data_ack


def test_the_probe_reply_goes_through_it():
    import inspect
    from nucleo.flash import probe_after
    assert "_dback.backed(" in inspect.getsource(probe_after.the_words_it_owes)


def test_every_rotating_ack_of_the_voice_is_a_bare_done():
    """The voice picks its ack among `data_acks` so two ops in a row are not said alike (V2-038); every variant is
    the same bare claim and is checked the same way (audit V2-783 P0-2)."""
    spec.open(BODY, text="give me the carbonara recipe", widget="documento")
    for ack in list(getattr(_lang(), "data_acks", None) or ()) + [_lang().data_ack]:
        assert done_backing.backed(ack, "widget_data", {"ops": [{"widget": "documento"}]}) == _lang().done_not_on_card, ack


def test_the_voice_ack_is_checked_against_the_cards_too():
    import inspect
    from nucleo.flash import post_stream_settle
    src = inspect.getsource(post_stream_settle.settle_what_is_pending)
    assert "_dback.backed(spoken_text, \"widget_data\"" in src, "the voice channel's canned ack must go through done_backing"
