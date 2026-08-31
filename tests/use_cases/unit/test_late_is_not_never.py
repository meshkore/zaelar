"""“Never delivered” and “delivered late” call for fixing different things, and the judge did not know which one it was (V2-286).

`sheet_timing` has measured since V2-227 when the sheet was opened and when the first named row was written. During
all that time **nobody has read it**: neither the judge nor the report. A measured number that nobody consumes is not
a measurement; it is a file.

And it is precisely what separates the two readings. Its absence can be seen in the judge’s own sheet section, which
says “Watch the TIMING: it may have been filled in AFTER the last turn” — the possibility is pointed out to it, but
it is never given the FACT. Measured in the 2026-08-24 03:48 batch, with the four cases:

    monitor  4/5   primera fila 13,2 s ANTES del último turno   → había qué entregar, y entregó
    camera   2/5   primera fila 37,1 s ANTES                    → había qué entregar (falló la conducta)
    guitar   3/5   primera fila  1,6 s DESPUÉS                  → en la conversación no había nada
    bicycle  2/5   sin primera fila                             → no se encontró nada

⚠️ And it corrects one of my readings: when I saw that all three delivered on turn 9 of 10, I wrote that the dominant
problem was LATENCY. The number says no — in two of the four cases, the sheet had been full for half a minute when
they spoke. The suspicion was reasonable, and the data disproves it, which is what measurement is for.
"""
from tests.use_cases.e2e.agent import judge as J

_BASE = {"families_observed": ["worker", "widget"], "expected_signals": [], "missing_signals": [],
         "results_sheet": {"read": True, "n_items": 6, "n_named": 6, "n_backed": 6,
                           "n_sites_reported": 1, "titles": ["Nikon D3100"]}}


def _facts(after_s):
    m = dict(_BASE)
    m["sheet_timing"] = {"first_result_ms": 1000.0, "last_turn_ms": 1000.0 - (after_s * 1000.0),
                         "after_last_turn_s": after_s}
    return J.mechanism_facts(m)


def test_llegar_DESPUES_del_ultimo_turno_se_llama_latencia_y_no_ocultacion():
    f = _facts(1.6)
    assert "DESPUÉS del último turno" in f
    assert "LATENCIA" in f
    assert "no que zaelar se callara" in f, (
        "sin desmentir la lectura fácil, el juez la escribe igual — es lo que hizo en dos casos")


def test_llegar_ANTES_deja_el_fallo_donde_estaba_la_conducta():
    """The other half, and the one that prevents this from becoming an amnesty: with the sheet full while they
    speak, failing to deliver IS behavior."""
    f = _facts(-37.1)
    assert "ANTES del último" in f
    assert "fallo de conducta" in f
    assert "LATENCIA" not in f


def test_sin_el_dato_no_se_afirma_ninguna_de_las_dos():
    """`None` means “I did not measure it.” Filling it with zero would say “it arrived exactly on time,” which is a claim."""
    m = dict(_BASE)
    m["sheet_timing"] = {"first_result_ms": None, "last_turn_ms": None, "after_last_turn_s": None}
    f = J.mechanism_facts(m)
    assert "LATENCIA" not in f and "fallo de conducta" not in f


def test_el_numero_se_CALCULA_en_la_ronda():
    """The wiring half: the judge may know how to read it while the round fails to provide it (V2-199)."""
    import inspect

    from tests.use_cases.e2e.agent import run as R
    src = inspect.getsource(R)
    assert '"after_last_turn_s"' in src
    assert '"last_turn_ms"' in src, "sin el instante del último turno, la resta no se puede hacer"
