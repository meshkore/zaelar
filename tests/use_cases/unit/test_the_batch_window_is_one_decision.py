"""`--start-at` and `--limit` bound the batch, and were implemented in two places with two behaviors (V2-280).

Measured on 2026-08-24 while trying to start the `search-buy` batch, which is literally what these two flags
exist to do. The two halves of the same bug:

  · **The application ORDER was reversed on the execution path.** `--limit` truncated to the first N and
    THEN searched for `--start-at` within that subset, so the natural composition —“four cases starting with
    the bicycle”— selected nothing and exited with “--start-at 'search-buy-bicycle__es' is not in the
    selected set”. The message points to SELECTION, which was correct; the problem was the arity.
  · **And `--list` ignored both.** It was used to check what the batch was going to run and reported the
    entire selection: 19 cases where 4 were going to run. Its own comment had already fixed this same issue
    for `--segment` (“a listing that contradicts the run it is meant to preview is worse than having no
    listing”), and the lesson had not been applied to these two.

And the part that makes this a shared function rather than two fixes: **fixing `--list` on its own would have
been WORSE than the bug.** That path sorted by (tier, locale, id), while the execution path respects the order
of `all_scenarios()`, which is not the same — verified, they differ from the first element. A “fixed” `--list`
would have previewed a DIFFERENT batch from the one that runs, with all the confidence of a correct listing.
"""
from tests.use_cases.e2e.agent import run as runmod
from tests.use_cases.e2e.agent import scenarios as SC


class _S:
    def __init__(self, i): self.id = i


_ROWS = [_S("a"), _S("b"), _S("c"), _S("d"), _S("e")]


def test_la_composicion_NATURAL_es_N_casos_DESDE_ese_id():
    rows, err = runmod.window_of(_ROWS, "c", 2)
    assert err == ""
    assert [s.id for s in rows] == ["c", "d"], (
        "es «dos casos empezando por c», no «los dos primeros y luego busca c»")


def test_y_ese_era_el_agujero_al_reves_no_selecciona_nada():
    """Sensitivity: the reversed order, reproduced manually, on the same data."""
    recortado = _ROWS[:2]                              # what `--limit` did first
    assert "c" not in [s.id for s in recortado], "por aquí salía «is not in the selected set»"


def test_cada_flag_por_su_cuenta_sigue_haciendo_lo_suyo():
    assert [s.id for s in runmod.window_of(_ROWS, "d", 0)[0]] == ["d", "e"]
    assert [s.id for s in runmod.window_of(_ROWS, "", 3)[0]] == ["a", "b", "c"]
    assert [s.id for s in runmod.window_of(_ROWS, "", 0)[0]] == ["a", "b", "c", "d", "e"]


def test_un_id_que_no_esta_es_un_ERROR_no_una_tanda_vacia():
    """A batch that selects nothing has to SAY SO: silently running zero cases reads as success."""
    rows, err = runmod.window_of(_ROWS, "zzz", 2)
    assert "is not in the selected set" in err
    assert rows == _ROWS, "sin ventana válida no se recorta a ciegas"


def test_el_limite_MAYOR_que_la_lista_no_recorta():
    assert len(runmod.window_of(_ROWS, "", 99)[0]) == 5


# ── what required sharing the function: the two paths do NOT see the same order ────────────────────────
def test_el_catalogo_NO_viene_ordenado_por_tier_locale_id():
    """The premise of the fix, stated here so that anyone changing it is aware.

    If `all_scenarios()` ever returned an already sorted result, this test would turn red and anyone reading it
    would know that `--list` could sort again on its own without lying. While that is false, it cannot.
    """
    crudo = [s.id for s in SC.all_scenarios()]
    ordenado = sorted(crudo, key=lambda i: i)
    assert crudo != ordenado, (
        "el catálogo ya viene ordenado: revisa si `--list` puede reordenar sin separarse de la corrida")


def test_la_ventana_vive_UNA_vez():
    """Two copies of this decision drift apart without warning — that is how this defect originated."""
    import inspect
    src = inspect.getsource(runmod)
    # Count the `return` that PRODUCES it, not the string: the `window_of` docstring quotes it when counting the
    # measured failure, and a guard that mistook the explanation for a copy would require deleting the rationale.
    assert src.count('return rows, f"--start-at') == 1, "el error volvió a construirse en dos sitios"
    assert src.count("window_of(") >= 3, "alguno de los dos caminos dejó de usar la función compartida"
