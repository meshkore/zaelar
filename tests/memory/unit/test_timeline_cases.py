"""Tests for tests/memory/e2e/timeline/cases.py — the REAL seed-reproducible segment (V2-105, 2026-08-17).

Purely structural/deterministic: it does not touch the timeline DB (the manual/expensive e2e runner does that). They catch
the class of bug found while building this: a deferred resolution scheduled outside the loop's range is
silently lost, and a `slot` checkpoint without `not_marker` ALWAYS fails (`"" in text` is true in Python).
"""
from tests.memory.e2e.timeline import cases as C


def test_seed_is_reproducible():
    """Same seed → same cases, always — the variety is CONTROLLED, not true randomness."""
    import importlib
    first = list(C.CASES)
    importlib.reload(C)
    second = list(C.CASES)
    assert first == second


def test_real_tramo_days_stay_within_bounds():
    for case in C.CASES:
        assert 0 <= case["day"] <= C.TOTAL_DAYS, f"caso fuera de rango: {case}"


def test_no_deferred_resolution_falls_outside_the_loop():
    """The actual bug class: a `resolve_at[day + gap]` with day+gap > TOTAL_DAYS is never executed — the
    initial write is silently left without its verification checkpoint. Every `slot`/`recall` case in the
    actual segment must have a counterpart: for every synthetic slot (`goal.job.N`, `pref.transport.N`…) that
    appears in a `write`, there must be at least one later `slot` that checks it.
    """
    real_cases = [c for c in C.CASES if c["day"] > C.DAYS]
    written_slots = {c["slot"] for c in real_cases if c.get("op") == "write" and c.get("slot")}
    checked_slots = {c["slot"] for c in real_cases if c.get("op") == "slot"}
    missing = written_slots - checked_slots
    assert not missing, f"slots escritos sin checkpoint de verificación (resolución perdida fuera de rango): {missing}"


def test_every_slot_checkpoint_has_both_marker_and_not_marker():
    """The actual bug found: `_execute()`'s `op=='slot'` treats a missing `not_marker` as an empty string, and
    `"" in text` is ALWAYS true — a checkpoint without `not_marker` fails no matter what. Every new `slot`
    case must include both fields."""
    for case in C.CASES:
        if case.get("op") != "slot":
            continue
        assert case.get("marker"), f"caso slot sin marker: {case}"
        assert case.get("not_marker"), f"caso slot sin not_marker (fallaría SIEMPRE): {case}"


def test_contradiction_written_values_differ_from_excluded_value():
    """For each contradiction, the final written value (marker) and the excluded value (not_marker) must be
    literally different — if they were the same, the checkpoint would be trivially unsatisfiable."""
    real_cases = [c for c in C.CASES if c["day"] > C.DAYS and c.get("op") == "slot"]
    for case in real_cases:
        assert case["marker"] != case["not_marker"], f"marker == not_marker, checkpoint imposible: {case}"


def test_real_tramo_generates_all_three_new_shapes():
    real_cases = [c for c in C.CASES if c["day"] > C.DAYS]
    slot_titles = " ".join(c["title"] for c in real_cases if c.get("op") == "slot")
    assert "corrige" in slot_titles or "confirma" in slot_titles, "faltan casos de contradicción/confirmación"
    assert "competencia" in slot_titles, "faltan casos de hecho en competencia"
    recall_titles = [c["title"] for c in real_cases if c.get("op") == "recall"]
    assert any("reformulada" in t for t in recall_titles), "faltan casos de paráfrasis diferida"


def test_platform_group_covers_full_extended_corpus():
    group = C.platform_group()
    assert group["count"] == len(C.CASES)
    assert group["cases"][-1]["dimension"] == f"día {C.TOTAL_DAYS}"
