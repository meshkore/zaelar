"""A report errand shows its skeleton FIRST and fills it as it goes (V2-831 T-25).

Demo pass 8, F1: the document card stayed empty for six minutes while the worker planned, thought and read sources,
because its delivery contract said to show the skeleton «once you have the structure» — which a worker that
researches first only has at the end. The format contract now puts the skeleton `show` right after the plan,
before any search or read, and each section is appended as soon as it exists (write early, refine later).

Disarm: put «once you have the structure» back → red.
"""
from __future__ import annotations


def test_the_skeleton_show_is_the_first_step_after_the_plan_before_any_search():
    from nucleo.workers.prompts import DOC_SURFACE_BLOCK as b
    i_first = b.find("PRIMER PASO DESPUÉS DEL PLAN")
    assert i_first >= 0, "the contract no longer names WHEN the skeleton goes: first, after the plan"
    tail = b[i_first:]
    assert tail.index("antes de buscar o leer nada") < tail.index("`show` con el esqueleto"), \
        "the skeleton is no longer ahead of the research"
    assert "En cuanto tengas la estructura" not in b


def test_each_section_is_appended_as_soon_as_it_exists():
    from nucleo.workers.prompts import DOC_SURFACE_BLOCK as b
    assert "data documento append" in b and "EN CUANTO la tengas" in b and "afina después" in b


def test_the_contract_reaches_the_worker_on_a_document_errand():
    from nucleo import surfaces
    from nucleo.workers import prompts
    assert prompts.DOC_SURFACE_BLOCK in prompts.trusted_blocks(surfaces.DOC)
