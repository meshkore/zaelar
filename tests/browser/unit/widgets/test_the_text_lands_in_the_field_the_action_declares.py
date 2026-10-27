"""The text a model writes lands in the field the action declares as its text (2026-10-27).

«Dame la receta de la carbonara» (docs-single-recipe-not-a-list__es): the model wrote the whole recipe into
`documento:show {title, content}`. `show` declares its free text as `body` (`"text_field": "body"`); `content` is
declared nowhere, so the sheet opened EMPTY — «Te la abro» over nothing — and a worker then spent minutes rewriting
what had been dropped. The synonym table in `contract.py` is a word list and only shrinks; this rule reads no words:
the action's declared text field, empty, and exactly ONE undeclared field holding text. Nothing else moves.
"""
from __future__ import annotations

from widgets import contract as C

RECIPE = "# Carbonara\n\n400 g de espaguetis, guanciale, yemas, pecorino, pimienta."


def test_the_one_loose_text_becomes_the_declared_text_field():
    out = C.fold_aliases("documento", "show", {"title": "Receta", "content": RECIPE})
    assert out["body"] == RECIPE


def test_any_spelling_of_the_loose_field_is_read_the_same():
    for loose in ("receta_md", "markdown", "texto_completo"):
        assert C.fold_aliases("documento", "show", {"title": "R", loose: RECIPE})["body"] == RECIPE


def test_two_loose_texts_are_ambiguous_and_nothing_moves():
    out = C.fold_aliases("documento", "show", {"title": "R", "content": RECIPE, "notes": "otra cosa"})
    assert "body" not in out


def test_a_declared_text_is_never_overwritten():
    out = C.fold_aliases("documento", "show", {"title": "R", "body": "lo suyo", "content": RECIPE})
    assert out["body"] == "lo suyo"


def test_an_action_that_declares_no_text_field_is_left_alone():
    out = C.fold_aliases("documento", "goto", {"heading": "Pasos", "content": RECIPE})
    assert "body" not in out
