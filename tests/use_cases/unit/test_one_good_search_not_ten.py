"""One well-aimed search is the target; ten is thrashing, zero is a broken resource.

Operator's norm, 2026-08-20: "a use case is ONE search — you think through a few things and do
a single search". The judge sees a number and tends to read more as more effort; in the round that
did fifteen, the worker was circling the same query without changing its criteria. And zero is not
"found nothing" — it is never having gone out to look, which is a different defect with a different
owner and must not be graded as a failed search.
"""
from tests.use_cases.e2e.agent import judge


def _brief(n):
    return judge.mechanism_facts({"search_health": {"n_search_events": n, "degraded": False}})


def test_zero_rows_is_not_reported_as_not_having_searched():
    """Verified in the tree 2026-08-20: the WORKER's search bridge emits nothing at all, so a zero counts
    which door searched, not whether a search happened. An errand resolved entirely by the worker reads
    zero and is healthy. This nearly went out as "the search engine turns itself off"."""
    out = _brief(0)
    assert "no concluyas ni que buscó ni que no buscó" in out
    assert "no salió a mirar" not in out


def test_one_search_gets_no_scolding_either_way():
    out = _brief(1)
    assert "Cero FILAS" not in out and "DAR VUELTAS" not in out


def test_many_searches_are_thrashing_not_diligence():
    out = _brief(15)
    assert "DAR VUELTAS" in out


def test_the_boundary_is_not_crossed_by_a_couple_of_refinements():
    """Two or three passes while narrowing criteria are legitimate; the line is well above that."""
    assert "DAR VUELTAS" not in _brief(3)
