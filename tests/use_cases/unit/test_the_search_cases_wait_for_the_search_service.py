"""The search use cases wait for the search service (V2-782, operator 2026-10-10).

«Hay que marcar los use cases relacionados, así que no merece la pena trabajar en ellos hasta que esté a tope el
sistema de búsqueda.» Every completable case whose deliverable is a shortlist on the results sheet is gated by
V2-782 F6, in both languages; the canaries (inline fact, recipes, images, documents) keep running.
"""
from tests.use_cases.e2e.agent import segments


def test_a_shortlist_case_is_gated_by_the_search_service():
    for sid in ("best-rated-rental-car", "compare-insurance-quotes__us", "cheapest-monitor", "hotel-under-15-days__us"):
        assert "V2-782 F6" in segments.blocked_by(sid), sid


def test_the_canaries_still_run():
    for sid in ("quick-fact-opening-hours", "docs-report-lands-as-document__us", "show-real-photo-of-a-new-car",
                "agenda-everyday-edits", "build-workout-tracker-widget__us"):
        assert not segments.blocked_by(sid), sid


def test_a_case_with_its_own_gate_keeps_it():
    assert "V2-260 F2" in segments.blocked_by("candidates-already-known")
