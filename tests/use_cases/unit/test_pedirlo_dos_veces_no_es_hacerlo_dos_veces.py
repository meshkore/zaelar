"""V2-442 · an errand requested twice and ABSORBED is not duplicated work.

Deduplication (`dispatch.find_duplicate`) absorbs the second escalation without launching a worker. When that
happens, there is no duplicated navigation: there is an unnecessary escalation decision, which costs one turn.
The judge received «the same errand was launched twice … score EFFICIENCY down» without knowing how many workers
were BORN, and filed it as «duplicates navigation work».

Measured on 2026-08-28 in `buy-known-product__us`: two escalations with IDENTICAL text (Jaccard 1.0) and
`n_spawned: 1` — a single worker. Fourth case that night of an instrument accusing the product of something it
did not do, and the one repeated most often in the sweep: of 214 rounds with the signal, 15 contain an identical
duplicate, and in the last four deduplication absorbed it.

And it is NOT absolved wholesale, because the real case exists and is measured: on August 24 and 25 there were
groups of two and three errands with THREE workers born. What matters is how many were born.
"""
from tests.use_cases.e2e.agent import judge


def _mech(n_spawned, n=2):
    return {"duplicate_errands": {"read": True, "worst": n, "identical_repeats": 1,
                                  "n_spawned": n_spawned,
                                  "groups": [{"n": n, "goal": "busca una bici", "identical": True}]}}


def _linea(mech):
    for l in judge.mechanism_facts(mech).splitlines():
        if "PIDIÓ" in l or "DUPLICADOS" in l:
            return l
    return ""


def test_absorbido_por_el_dedup_NO_se_puntua_como_trabajo_duplicado():
    l = _linea(_mech(1))
    assert "NO hubo trabajo duplicado" in l and "absorbió" in l
    assert "DUPLICADOS" not in l


def test_si_NACIERON_los_dos_sigue_siendo_el_defecto_de_siempre():
    """The part that prevents the fix from being an amnesty: with two live workers, the work really WAS done two
    times, and that cost real minutes of navigation on August 24 and 25."""
    l = _linea(_mech(3))
    assert "DUPLICADOS" in l and "SÍ se hizo por duplicado" in l


def test_sin_saber_cuantos_nacieron_se_mantiene_la_ADVERTENCIA():
    """Fail-closed: «I don't know» cannot absolve. An old round without the field must continue to be read
    as before, or the fix would erase findings already archived."""
    m = _mech(1)
    m["duplicate_errands"].pop("n_spawned")
    assert "DUPLICADOS" in _linea(m)


def test_la_linea_DICE_cuantos_nacieron_en_las_dos_ramas():
    """Without the number, the report has to be reopened to know what is being discussed — which is exactly what
    it took to discover this false positive."""
    assert "1 worker" in _linea(_mech(1))
    assert "3 worker" in _linea(_mech(3))
