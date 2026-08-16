"""Tests de tests/memory/e2e/timeline/cases.py — el tramo REAL semilla-reproducible (V2-105, 2026-08-17).

Puramente estructural/determinista: no toca la BD del timeline (eso lo hace el runner e2e, manual/caro). Cazan
la clase de bug encontrada al construir esto: una resolución diferida programada fuera del rango del bucle se
pierde en silencio, y un checkpoint `slot` sin `not_marker` falla SIEMPRE (`"" in text` es cierto en Python).
"""
from tests.memory.e2e.timeline import cases as C


def test_seed_is_reproducible():
    """Misma seed → mismos casos, siempre — la variedad es CONTROLADA, no aleatoriedad real."""
    import importlib
    first = list(C.CASES)
    importlib.reload(C)
    second = list(C.CASES)
    assert first == second


def test_real_tramo_days_stay_within_bounds():
    for case in C.CASES:
        assert 0 <= case["day"] <= C.TOTAL_DAYS, f"caso fuera de rango: {case}"


def test_no_deferred_resolution_falls_outside_the_loop():
    """La clase de bug real: un `resolve_at[day + gap]` con day+gap > TOTAL_DAYS nunca se ejecuta — la
    escritura inicial queda sin su checkpoint de verificación, silenciosamente. Todo caso `slot`/`recall` del
    tramo real debe tener contrapartida: por cada slot sintético (`goal.job.N`, `pref.transport.N`…) que
    aparece en un `write`, debe existir al menos un `slot` posterior que lo compruebe.
    """
    real_cases = [c for c in C.CASES if c["day"] > C.DAYS]
    written_slots = {c["slot"] for c in real_cases if c.get("op") == "write" and c.get("slot")}
    checked_slots = {c["slot"] for c in real_cases if c.get("op") == "slot"}
    missing = written_slots - checked_slots
    assert not missing, f"slots escritos sin checkpoint de verificación (resolución perdida fuera de rango): {missing}"


def test_every_slot_checkpoint_has_both_marker_and_not_marker():
    """El bug real encontrado: `_execute()`'s `op=='slot'` trata `not_marker` ausente como cadena vacía, y
    `"" in text` es SIEMPRE cierto — un checkpoint sin `not_marker` falla pase lo que pase. Cualquier caso
    `slot` nuevo debe llevar los dos campos."""
    for case in C.CASES:
        if case.get("op") != "slot":
            continue
        assert case.get("marker"), f"caso slot sin marker: {case}"
        assert case.get("not_marker"), f"caso slot sin not_marker (fallaría SIEMPRE): {case}"


def test_contradiction_written_values_differ_from_excluded_value():
    """Para cada contradicción, el valor final escrito (marker) y el excluido (not_marker) deben ser
    literalmente distintos — si coincidieran, el checkpoint sería trivialmente insatisfacible."""
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
