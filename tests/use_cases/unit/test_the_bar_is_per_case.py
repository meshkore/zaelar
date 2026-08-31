"""The BAR is per case, and the opening line sounds like a person (operator, 2026-08-23).

Two changes, one request: “for some, the first result may be enough, while for others we will want to be
stricter and refine further” and “more like how a human would do it, with their imperfections”.

WHY A SINGLE BAR WAS WRONG. Every completable findings case was graded on one clause: «al menos 3
candidatos». A person with water coming through the bathroom ceiling wants ONE plumber who can come today
— delivering three and a comparison table is not a better answer, it is a slower one. A person comparing
insurers asked, literally, for a comparison. Holding both to the same bar marks the agent DOWN for doing
exactly what was asked in half the catalog.

WHY THE OPENING LINES CHANGED. 42 of 133 openings began «Búscame»/«Find»/«Encuéntrame» — a clean
imperative nobody types. The catalog `utterance` stays the canonical GOAL (the persona brief still anchors
on it, so the DRIVE model always knows what it wants); the profile's opening is how a person would ask for
it out loud, with the detail they only remember a turn later.

The load-bearing guard here is the LAST one: both changes are applied at `scenarios.all_scenarios()`, the
single point `apply_data_note` and `apply_findings_contract` already share — because three of the findings
cases (`hotel-under-15-days`, `search-buy-used-car`, `cheapest-monitor`) are hand-written and never pass
through `derive()`. Applied in `derive()` alone, half the catalog would silently keep the old bar.
"""
from __future__ import annotations

import pytest

from tests.use_cases.e2e.agent import derived as D
from tests.use_cases.e2e.agent import scenarios as SC
from tests.use_cases.e2e.agent import segments as G


# ── the bar itself ─────────────────────────────────────────────────────────────────────────────────────────

def test_the_bars_are_a_closed_vocabulary():
    """Open-ended bars would drift into per-case prose, which is what `success_extra` is already for."""
    assert D.BARS == ("primero_valido", "comparar", "afinar")
    for bare, prof in D.PROFILES.items():
        assert prof.bar in D.BARS, f"{bare}: vara desconocida {prof.bar!r}"


def test_an_unprofiled_case_keeps_the_bar_the_32_measured_rounds_used():
    """`comparar` is the default on purpose: every historical verdict on the board was scored against it,
    so a case nobody has classified must not silently change what its old score meant."""
    assert D.bar_of("a-case-that-does-not-exist") == "comparar"
    assert D.Profile().bar == "comparar"


@pytest.mark.parametrize("bar,present,absent", [
    ("primero_valido", "UNO BUENO BASTA", "al menos 3 candidatos"),
    ("comparar", "al menos 3 candidatos", "MODO EXIGENTE"),
    ("afinar", "MODO EXIGENTE", None),
])
def test_each_bar_states_its_own_deliverable(bar, present, absent):
    text = D.deliverable_findings(bar)
    assert present in text
    if absent:
        assert absent not in text


def test_every_bar_keeps_the_floor_that_is_not_negotiable():
    """The bar moves clause (a) — HOW MUCH counts as delivered. It must never move the rest: read the page
    (not the model's memory), respect the stated criteria, put it on the generic sheet and never a new
    widget, say so when it could not, and ASK for a missing location instead of picking a city."""
    for bar in D.BARS:
        text = D.deliverable_findings(bar)
        assert "SE PUEDE COMPLETAR DE INICIO A FIN" in text, bar
        assert "HOJA DE RESULTADOS" in text, bar
        assert "widget NUEVO" in text, bar
        assert "PREGUNTARLA es lo correcto" in text, bar
        # …and the anti-hallucination clause survives in EVERY bar, including the fast one. A case where
        # one result is enough is exactly where inventing that one result is cheapest.
        assert "el fallo MÁS GRAVE" in text, bar


def test_the_relaxed_bar_still_demands_a_real_source():
    """`primero_valido` lowers the COUNT, never the evidence. “One is enough” must not read as “one from memory”."""
    text = D.deliverable_findings("primero_valido")
    assert "LEÍDO de la página real" in text
    assert "de dónde sale" in text


def test_the_strict_bar_asks_for_what_a_comparison_actually_is():
    """A list of three is not a comparison: each candidate has to be placed against EACH stated criterion,
    the winner has to be named with its reason, and an unverifiable criterion has to be declared."""
    text = D.deliverable_findings("afinar")
    assert "CADA criterio" in text
    assert "el mejor tiene que venir señalado" in text
    assert "no se da por bueno" in text


def test_both_bars_are_actually_used_by_real_cases():
    """A vocabulary nobody assigns is dead code that reads like a feature."""
    used = {D.bar_of(G.bare(s.id)) for s in SC.all_scenarios() if G.delivers_findings(s.id)}
    assert "primero_valido" in used
    assert "afinar" in used
    assert "comparar" in used, "el defecto tiene que seguir cubriendo la mayoría, no vaciarse"


def test_a_case_carries_exactly_the_clause_of_its_own_bar():
    """End to end through the real catalog — the wiring, not the builder."""
    for scn in SC.all_scenarios():
        if not G.delivers_findings(scn.id):
            continue
        bar = D.bar_of(G.bare(scn.id))
        expect = {"primero_valido": "UNO BUENO BASTA", "afinar": "MODO EXIGENTE",
                  "comparar": "al menos 3 candidatos"}[bar]
        assert expect in scn.success_checks, f"{scn.id}: vara {bar} sin su cláusula"


def test_market_twins_share_a_bar():
    """A bar is keyed by BARE id, so an ES case and its derived US twin cannot be graded differently — the
    same guard `test_market_twins_are_held_to_the_same_bar` already applies to signals and turn budget."""
    by_bare: dict[str, set] = {}
    for scn in SC.all_scenarios():
        if G.delivers_findings(scn.id):
            by_bare.setdefault(G.bare(scn.id), set()).add(D.bar_of(G.bare(scn.id)))
    for bare, bars in by_bare.items():
        assert len(bars) == 1, f"{bare}: gemelos con varas distintas {bars}"


# ── the opening line ───────────────────────────────────────────────────────────────────────────────────────

def test_a_profile_opening_replaces_the_catalog_imperative():
    scn = next(s for s in SC.all_scenarios() if s.id == "best-plumber-same-day__es")
    assert "fuga en el baño" in scn.opening_line
    assert not scn.opening_line.startswith("Búscame")


def test_a_hand_written_opening_is_never_overwritten_by_a_profile():
    """THE guard of this change, and it arrived as a FAILURE rather than a design.

    The first version applied the profile opening everywhere, including hand-written scenarios — which put
    `test_handwritten_scenarios_are_never_shadowed_by_a_derived_one` (test_multiflow.py) straight into the
    red for `cheapest-monitor`. It was right: an authored scenario already owns its opening in its own file,
    so a second authored version in `derived.PROFILES` would be two homes for one sentence. The profile
    serves the DERIVED twins; the scenario keeps its own line."""
    scn = next(s for s in SC.all_scenarios() if s.id == "cheapest-monitor")
    prof = D.PROFILES["cheapest-monitor"]
    assert prof.opening_es, "el caso derivado sí declara apertura humana (esto es lo que se ignora aquí)"
    assert scn.opening_line != prof.opening_es
    assert scn.opening_line == SC.BY_ID["cheapest-monitor"].opening_line


def test_the_derived_twin_of_a_hand_written_case_still_gets_it():
    """The other half of the exemption: skipping the hand-written ES scenario must not skip its US twin,
    which is derived and has no authored opening of its own."""
    scn = next(s for s in SC.all_scenarios() if s.id == "cheapest-monitor__us")
    assert "my work monitor is dying" in scn.opening_line


def test_a_case_with_no_human_opening_keeps_the_catalog_utterance():
    """Fail-soft: the rewrite is opt-in per case, so an unedited case must be byte-identical to before.

    Scoped to DERIVED scenarios, and the scoping is a finding rather than a convenience: a HAND-WRITTEN
    scenario is allowed its own opening by construction (`search-buy-used-car` already had one, softer than
    its catalog row, long before this change). Asserting over those would have demanded that hand-written
    authorship stop existing.
    """
    from tests.use_cases import cases_data as CD
    from tests.use_cases.e2e.agent import dates as DT
    by_id = {(c.id, c.locale): c for c in CD.CASES}
    untouched = 0
    for scn in SC.all_scenarios():
        if scn.id in SC.BY_ID:
            continue                       # hand-written: its opening IS the authored one
        bare = G.bare(scn.id)
        prof = D.PROFILES.get(bare)
        if prof is not None and (prof.opening_es or prof.opening_us):
            continue
        case = by_id.get((bare, scn.locale))
        if case is None:
            continue                       # no catalog row to compare against
        # Contrary to the RESOLVED text: dates are relative to today (operator rule 2026-08-19), and the
        # record replaces its tokens, just as in `test_handwritten_scenarios_are_never_shadowed…`.
        assert scn.opening_line == DT.resolve(case.utterance), scn.id
        untouched += 1
    assert untouched > 50, "el fallback dejó de cubrir el grueso del catálogo"


def test_an_english_case_never_receives_the_spanish_opening():
    """`opening_es`/`opening_us` are separate fields, and a US persona handed a Spanish line would be
    steered out of character on its very first turn (the same bias V2-... fixed in the driver)."""
    for scn in SC.all_scenarios():
        prof = D.PROFILES.get(G.bare(scn.id))
        if prof is None:
            continue
        if scn.locale == "us" and prof.opening_es and not prof.opening_us:
            assert scn.opening_line != prof.opening_es, scn.id


def test_the_goal_survives_a_crooked_opening():
    """The whole design rests on this: the opening may be vague, hedged or missing a detail, because the
    persona brief still anchors the GOAL on the catalog's canonical `utterance`. Without it, a softer
    opening would just be a vaguer test."""
    from tests.use_cases import cases_data as CD
    case = next(c for c in CD.CASES if c.id == "best-plumber-same-day" and c.locale == "es")
    scn = next(s for s in SC.all_scenarios() if s.id == "best-plumber-same-day__es")
    assert case.utterance in scn.persona_brief
    assert scn.opening_line != case.utterance


def test_the_openings_read_like_a_person_and_not_a_command():
    """The measured symptom was 42 catalog openings starting with a bare imperative. A rewritten one that
    still opens that way has not been rewritten."""
    starts = ("búscame", "encuéntrame", "find", "compárame", "resérvame", "compare")
    for bare, prof in D.PROFILES.items():
        for line in (prof.opening_es, prof.opening_us):
            if not line:
                continue
            first = line.split()[0].lower().strip("¿,")
            assert first not in starts, f"{bare}: la apertura humana sigue siendo un imperativo: {line[:60]}"


def test_the_driver_asks_for_human_imperfection_in_both_languages():
    """The per-case opening only covers the FIRST turn; every turn after it is generated by the DRIVE model
    from its anchor, so the instruction has to live there too — and in both anchors, or the US half keeps
    producing tidy prose."""
    from tests.use_cases.e2e.agent import driver as drivermod
    assert "IMPERFECCIÓN" in drivermod._ANCHOR
    assert "IMPERFECTION" in drivermod._ANCHOR_EN
    for anchor in (drivermod._ANCHOR, drivermod._ANCHOR_EN):
        assert "lista" in anchor.lower() or "lists" in anchor.lower()
