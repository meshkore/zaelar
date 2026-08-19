"""Ratchet for the catalog SEGMENTATION (`e2e/agent/segments.py`).

The point of these tests is not to restate the table — it is to make the two failure modes that already
happened impossible to repeat silently:

  · a case added to the catalog and never classified (it would be run against the wrong bar, or excluded from
    the runnable list, with no error anywhere);
  · a case whose grading note contradicts what the user actually asked for.
"""
from __future__ import annotations

from tests.use_cases.e2e.agent import derived as D
from tests.use_cases.e2e.agent import scenarios as SC
from tests.use_cases.e2e.agent import segments as G


def test_every_scenario_in_the_catalog_is_classified():
    """CLOSED inventory. A case with no segment is a bug, never a state — it has no answer to "can this be
    tested end to end?", which is the question the whole board now hangs off."""
    unclassified = sorted({G.bare(s.id) for s in SC.all_scenarios() if G.segment_of(s.id) is None})
    assert not unclassified, f"casos sin clasificar en segments.SEGMENTS: {unclassified}"


def test_no_classification_points_at_a_case_that_no_longer_exists():
    """The other direction: a stale entry survives a rename and quietly stops applying to anything."""
    live = {G.bare(s.id) for s in SC.all_scenarios()}
    dead = sorted(set(G.SEGMENTS) - live)
    assert not dead, f"clasificados que ya no están en el catálogo: {dead}"


def test_the_three_groups_are_the_only_ones():
    groups = {seg.group for seg in G.SEGMENTS.values()}
    assert groups <= {G.COMPLETABLE, G.CREDENTIALS, G.CAPABILITY}


def test_a_completable_case_is_graded_on_its_WHOLE_outcome():
    """No real-data note, in either direction: the note tells the judge not to penalise an unfinished outcome,
    and on a case that CAN finish that is an excuse for a real failure."""
    for scn in SC.all_scenarios():
        if not G.is_completable(scn.id):
            continue
        assert D.data_scope(G.bare(scn.id)) == ("", ""), scn.id
        assert "LÍMITE DE DATOS REALES" not in scn.success_checks, scn.id
        assert "CAPACIDAD QUE NO EXISTE" not in scn.success_checks, scn.id


def test_every_blocked_case_says_what_is_missing():
    """The reverse guard. A blocked case with no note would be graded as if it could finish — which is how a
    batch produces five "failures" that are really five missing credentials."""
    for scn in SC.all_scenarios():
        seg = G.segment_of(scn.id)
        if seg.group == G.COMPLETABLE:
            continue
        assert seg.missing, scn.id
        assert seg.grade in ("no_account", "no_booking"), scn.id
        assert ("LÍMITE DE DATOS REALES" in scn.success_checks
                or "CAPACIDAD QUE NO EXISTE" in scn.success_checks), scn.id


def test_a_capability_gap_is_not_described_as_a_missing_operator_datum():
    """`_DATA_NOTE_ACCOUNT` tells the judge the missing piece is "no por un fallo del sistema". True of a bill
    the operator never had; FALSE of a WhatsApp we cannot send — and the judge reads exactly that sentence to
    decide whether the agent's excuse was legitimate."""
    note = D.data_note("coordinate-lunch-whatsapp")
    assert "CAPACIDAD QUE NO EXISTE" in note
    assert "Ninguna credencial lo desbloquea" in note
    assert "no por un fallo del sistema" not in note
    # …and the operator-datum wording is still used where it IS accurate.
    assert "no por un fallo del sistema" in D.data_note("pay-known-bill")


def test_the_group_is_NOT_derivable_from_the_case_id():
    """Why this table is hand-edited and not a heuristic: these two share a prefix, a tier and a shape, and
    differ only in that one utterance ends in «y cómpramelo». That one word decides whether the case can be
    carried out end to end, and any regex over the id would put them together."""
    assert G.group_of("search-buy-guitar") == G.COMPLETABLE
    assert G.group_of("search-buy-book") == G.CREDENTIALS


def test_the_completable_list_is_not_empty_and_not_everything():
    """A segmentation that classified everything one way would pass every test above and be useless."""
    groups = [G.group_of(s.id) for s in SC.all_scenarios()]
    for g in (G.COMPLETABLE, G.CREDENTIALS, G.CAPABILITY):
        assert groups.count(g) >= 5, f"grupo {g} sospechosamente pequeño: {groups.count(g)}"
