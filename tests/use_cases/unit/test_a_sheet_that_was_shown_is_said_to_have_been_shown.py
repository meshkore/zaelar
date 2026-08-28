"""V2-469 · when every written sheet was shown, the judge is TOLD — or it reconstructs the opposite.

Measured in `find-videos-on-a-topic-no-ai-slop` (2026-08-28 22:11): the mechanism had already measured
visibility (`sheet_instances.n_unseen: 0`, `unseen_ids: []`), but nothing said it in words. The judge,
reading raw `widget_ops` — where a scoped box's `show` lands under its family key (`results`), never
under `results::<id>` — filed [alta] «el widget de resultados nunca recibió la orden de mostrarse» over
a sheet the operator had on screen. Same family as the single-event span read as 0ms (V2-468/2): a raw
counter without its meaning enunciated reads like evidence of the opposite.
"""
from tests.use_cases.e2e.agent import judge


def _facts(si):
    return judge.mechanism_facts({
        "results_sheet": {"read": True, "n_items": 4, "n_named": 4, "n_backed": 4,
                          "titles": ["A", "B", "C", "D"], "n_sites_reported": 3},
        "sheet_instances": si,
    })


def test_the_measured_round_gets_the_positive_fact():
    """The real round's shape: 2 boxes, both seen → the judge is told visibility is already measured."""
    out = _facts({"n_sheets": 2, "ids": ["results", "results::3574e8-1"], "n_unseen": 0,
                  "unseen_ids": [], "written_ids": ["results::3574e8-1"], "n_errands": 2})
    assert "SE MOSTRARON" in out
    assert "no deduzcas visibilidad" in out


def test_an_actually_unseen_sheet_still_warns_and_never_reassures():
    """Sensitivity in the dangerous direction: a hidden sheet must keep its ⚠️ and NOT get the calm line."""
    out = _facts({"n_sheets": 2, "ids": ["results", "results::x-1"], "n_unseen": 1,
                  "unseen_ids": ["results::x-1"], "written_ids": ["results::x-1"], "n_errands": 2})
    assert "NADIE LAS ABRIÓ" in out
    assert "SE MOSTRARON" not in out


def test_no_written_sheets_means_no_line_at_all():
    """Nothing was written → asserting «all shown» would state a fact about boxes that don't exist."""
    out = _facts({"n_sheets": 0, "ids": [], "n_unseen": 0, "unseen_ids": [], "written_ids": [],
                  "n_errands": 0})
    assert "SE MOSTRARON" not in out
