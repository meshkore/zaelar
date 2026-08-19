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


# ── expected_signals: a CLOSED vocabulary, and it is not the one a human reads ─────────────────────────────

def test_every_expected_signal_is_a_real_observability_family():
    """`verify.mechanism_report` compares `expected_signals` against `verify.families_in()`, which returns the
    raw `cat` of each event — `worker`, `widget`, `memory`, `flash`, `system`. NOT the viewer's labels.

    This exists because the six discovery scenarios shipped with `["Brain Workers", "Widgets"]`, the
    human-readable family names from the observability panel. Nothing rejects an unknown string, so those cases
    would have reported BOTH signals MISSING on every run they ever had — a permanent mechanism failure with
    nothing to do with the agent. It went unnoticed only because they had not run yet. Read from
    `voice.observer._CAT`, the canonical map, so renaming a family there breaks this instead of drifting.
    """
    from voice import observer
    from tests.use_cases.e2e.agent import scenarios as SC
    known = set(observer._CAT.values()) | {"other"}
    for scn in SC.all_scenarios():
        unknown = [sig for sig in scn.expected_signals if sig not in known]
        assert not unknown, f"{scn.id}: señales que ninguna familia emite: {unknown} (válidas: {sorted(known)})"


def test_a_findings_case_must_require_the_results_SHEET():
    """A completable search/compare/plan case delivers findings the operator can LOOK at, which is a widget
    signal (V2-115: the generic `results` sheet, never a new widget). Requiring only `worker` let a run pass its
    mechanism check having produced nothing on screen.

    The two exceptions are deliberate and named: `quick-fact-opening-hours` is the in-turn `web_search` path
    where escalating at all is the failure (V2-022), and `remember-and-remind-deadline` delivers into memory and
    the scheduler, verified through `scheduled_jobs` rather than a family.
    """
    from tests.use_cases.e2e.agent import scenarios as SC
    from tests.use_cases.e2e.agent import segments as G
    exempt = {"quick-fact-opening-hours", "remember-and-remind-deadline"}
    for scn in SC.all_scenarios():
        if not G.is_completable(scn.id) or G.bare(scn.id) in exempt:
            continue
        assert "widget" in scn.expected_signals, f"{scn.id}: entrega hallazgos y no exige la hoja de resultados"


def test_market_twins_are_held_to_the_same_bar():
    """Signals and turn budget too, not just the data limit. `cheapest-monitor` (hand-written ES) asked for
    `worker`+`widget` in 10 turns while its DERIVED US twin fell back to `worker` in 8 — the same case graded
    differently depending on which side happened to be hand-written."""
    from tests.use_cases.e2e.agent import scenarios as SC
    from tests.use_cases.e2e.agent import segments as G
    by_bare: dict[str, list] = {}
    for scn in SC.all_scenarios():
        by_bare.setdefault(G.bare(scn.id), []).append(scn)
    for bare, group in by_bare.items():
        if len(group) < 2:
            continue
        shapes = {(tuple(sorted(s.expected_signals)), s.turns) for s in group}
        assert len(shapes) == 1, f"{bare}: los gemelos de mercado no tienen la misma vara: {shapes}"


# ── The findings contract: what a good answer CARRIES ──────────────────────────────────────────────────────

def test_every_findings_case_states_what_a_good_answer_must_carry():
    """A blocked case has a note saying what NOT to penalise. The completable ones had the opposite gap: one
    bland catalog sentence and nothing about the deliverable, so "encontré varias opciones interesantes" with no
    name, no price and nothing on screen could read as success.

    Applied at the SAME single point as the data note (`scenarios.all_scenarios`) so hand-written and derived
    cases share the bar — three hand-written findings cases (`hotel-under-15-days`, `search-buy-used-car`,
    `cheapest-monitor`) never pass through `derive()` and would otherwise have been graded more loosely than
    their own US twins.
    """
    from tests.use_cases.e2e.agent import scenarios as SC
    from tests.use_cases.e2e.agent import segments as G
    for scn in SC.all_scenarios():
        checks = scn.success_checks
        if G.delivers_findings(scn.id):
            assert "SE PUEDE COMPLETAR DE INICIO A FIN" in checks, scn.id
            assert "HOJA DE RESULTADOS" in checks, scn.id          # V2-115: the generic sheet…
            assert "widget NUEVO" in checks, scn.id                # …and a new widget is a FAILURE
            assert "al menos 3 candidatos" in checks, scn.id       # real options, not a vague "found some"
            assert checks.count("SE PUEDE COMPLETAR DE INICIO A FIN") == 1, scn.id
        else:
            assert "SE PUEDE COMPLETAR DE INICIO A FIN" not in checks, scn.id


def test_a_blocked_case_never_gets_the_findings_contract():
    """They contradict each other: one says the outcome is fully graded, the other says the outcome is withdrawn.
    A case carrying both would tell the judge two opposite things about the same run."""
    from tests.use_cases.e2e.agent import scenarios as SC
    for scn in SC.all_scenarios():
        both = ("SE PUEDE COMPLETAR DE INICIO A FIN" in scn.success_checks
                and ("LÍMITE DE DATOS REALES" in scn.success_checks
                     or "CAPACIDAD QUE NO EXISTE" in scn.success_checks))
        assert not both, f"{scn.id}: lleva el contrato de entrega Y el de límite, que se contradicen"


def test_a_findings_case_gets_a_turn_budget_a_real_search_can_fit_in():
    """A real browser search used 8-10 turns on its own in the measured rounds, and the contract's rule (e) makes
    ASKING for the missing location the correct opening move — which spends two more before the search starts.
    Two cases were at 8 while every other findings case ran at 10, so they were being failed for a budget their
    own criterion could not fit in."""
    from tests.use_cases.e2e.agent import scenarios as SC
    from tests.use_cases.e2e.agent import segments as G
    for scn in SC.all_scenarios():
        if G.delivers_findings(scn.id):
            assert scn.turns >= 10, f"{scn.id}: {scn.turns} turnos para una búsqueda real"
