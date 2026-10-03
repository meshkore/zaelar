"""When the verdict completes a turn the model left without a call, the row the MODEL named is the one acted on.

Demo pass 80 (2026-10-03), S3 «open the one that's the best deal» over the monitors sheet: the model called nothing
and said «the Samsung ViewFinity S7's ficha is open … at $189.99»; the verdict completed `results:detail` but filled
`index` with the operator's sentence, the op was rejected, and the next turn had to confess «the ficha never actually
opened». The model had read the sheet and named the row — a reading, like a number he said (`number_fill`).
"""
from __future__ import annotations

import pytest

from nucleo.flash import direct_action as DA
from nucleo.flash import payload_fill as PF

SHEET = [("Dell 27 Plus USB-C Monitor S2725QC 4K UHD", "$329.99"),
         ("LG UltraFine 27US550-W 27-inch 4K", "$229.99"),
         ("Samsung ViewFinity S7 27\" 4K UHD Monitor", "$189.99")]


@pytest.fixture
def sheet(monkeypatch):
    monkeypatch.setattr(PF, "_row_labels", lambda card: list(SHEET))


def test_the_row_named_by_title_and_price_is_its_index(sheet):
    said = "There you go — the Samsung ViewFinity S7's page is open, and at $189.99 it's the cheapest of the three."
    assert PF.row_named_fill("results", "detail", "results::x", said) == {"index": 3}


def test_a_price_alone_names_the_row(sheet):
    assert PF.row_named_fill("results", "detail", "results::x", "Opening the $229.99 one.") == {"index": 2}


def test_two_rows_named_equally_is_a_question_not_a_pick(sheet):
    said = "Between the Dell S2725QC and the Samsung ViewFinity — which one should I open?"
    assert PF.row_named_fill("results", "detail", "results::x", said) == {}


def test_words_that_name_no_row_fill_nothing(sheet):
    assert PF.row_named_fill("results", "detail", "results::x", "Which of the three do you mean?") == {}


def test_resolve_prefers_the_named_row_over_the_operators_sentence(sheet, monkeypatch):
    from nucleo import spec as S
    monkeypatch.setattr(DA, "from_brief", lambda brief: ("results", "detail"))
    monkeypatch.setattr(S, "gate_completion", lambda *a, **k: "")
    monkeypatch.setattr(DA, "card_to_present", lambda wid, text="": "results::x")
    rung = DA.resolve("open the one that's the best deal", brief={"x": 1},
                      operator_text="open the one that's the best deal",
                      model_words="Opening the Samsung ViewFinity S7 at $189.99.")
    assert rung["payload"] == {"index": 3} and rung["source"] == "model-named-row"
