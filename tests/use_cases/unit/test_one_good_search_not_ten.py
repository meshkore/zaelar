"""One well-aimed search is the target; ten is thrashing, zero is a broken resource.

Operator's norm, 2026-08-20: "un caso de uso es UNA búsqueda — te piensas unas cuantas cosas y haces
una única búsqueda". The judge sees a number and tends to read more as more effort; in the round that
did fifteen, the worker was circling the same query without changing its criteria. And zero is not
"found nothing" — it is never having gone out to look, which is a different defect with a different
owner and must not be graded as a failed search.
"""
from tests.use_cases.e2e.agent import judge


def _brief(n):
    return judge.mechanism_facts({"search_health": {"n_search_events": n, "degraded": False}})


def test_zero_searches_is_named_as_a_resource_that_was_not_used():
    out = _brief(0)
    assert "CERO búsquedas" in out and "no salió a mirar" in out


def test_one_search_gets_no_scolding_either_way():
    out = _brief(1)
    assert "CERO búsquedas" not in out and "DAR VUELTAS" not in out


def test_many_searches_are_thrashing_not_diligence():
    out = _brief(15)
    assert "DAR VUELTAS" in out


def test_the_boundary_is_not_crossed_by_a_couple_of_refinements():
    """Two or three passes while narrowing criteria are legitimate; the line is well above that."""
    assert "DAR VUELTAS" not in _brief(3)
