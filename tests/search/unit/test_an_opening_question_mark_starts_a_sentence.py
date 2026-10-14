"""A capitalised word right after an opening «¿» or «¡» starts a sentence, never a subject (node 2.637).

Reported beside the route work of 2026-10-14: `_CAPS` skipped a word after «. » or «? », but «¿Los tienes?» put «¿»
flush against the word, so «los» became a subject every row had to name. His commissioning sentence now reaches every
errand's sheet (node 2.630), where a question is the commonest shape of a request.
"""
from __future__ import annotations

from search import asked


def test_a_word_after_an_opening_mark_is_no_subject():
    assert asked.subjects("Vale. ¿Los tienes para el sábado?") == []
    assert asked.subjects("Oye, ¡Mira esto! busca un hotel") == []
    assert asked.subjects("y ¿Las entradas de Rosalía cuánto cuestan?") == ["rosalia"]


def test_a_real_subject_inside_a_question_still_counts():
    assert asked.subjects("¿Me buscas entradas de Bad Bunny en Madrid?") == ["bad bunny"]
