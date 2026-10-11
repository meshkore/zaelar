"""The search use cases ran again once the search service was live (V2-782 T6.1, 2026-10-11).

On 2026-10-10 every completable case whose deliverable is a shortlist on the results sheet was gated by V2-782 F6
(operator: «no merece la pena trabajar en ellos hasta que esté a tope el sistema de búsqueda»). The service shipped
the same day; the gate is now EMPTY and a shortlist case is runnable unless its segment names a gate of its own.
"""
from tests.use_cases.e2e.agent import segments


def test_a_shortlist_case_runs_now_that_the_search_service_is_live():
    assert segments.SEARCH_SERVICE_GATE == ()
    for sid in ("best-rated-rental-car", "compare-insurance-quotes__us", "cheapest-monitor", "hotel-under-15-days__us"):
        assert not segments.blocked_by(sid), sid


def test_the_canaries_still_run():
    for sid in ("quick-fact-opening-hours", "docs-report-lands-as-document__us", "show-real-photo-of-a-new-car",
                "agenda-everyday-edits", "build-workout-tracker-widget__us"):
        assert not segments.blocked_by(sid), sid


def test_a_case_with_its_own_gate_keeps_it():
    assert "V2-260 F2" in segments.blocked_by("candidates-already-known")
