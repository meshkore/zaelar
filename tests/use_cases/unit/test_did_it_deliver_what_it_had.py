"""V2-332 — of the rows the system put in front of it, how many did it actually name?

The report already knew what it was given (`results_sheet`) and what it said (`delivered_by_name`, V2-329/331). What was
missing was the CROSS-CHECK, which is the operator's question: not “did it deliver anything?” but **“did it deliver what it had?”**.

Measured in `search-buy-used-car__es` (2026-08-26 01:14) — the first round of the case with the extraction chain
fixed, and therefore the first one in which this question makes sense. The sheet contained five real cars,
all below the €12,000 limit:

    MINI Cooper F55 2016 — 11.700 €   ·   Audi Q5 2015 2.0TDI — 11.990 €
    FIAT Panda 4x4 diesel — 6.900 €   ·   Peugeot 5008 2.0HDI — 6.990 €
    Peugeot 3008 2010 — 3.490 €

and zaelar named THREE. The judge saw it —“ignore better valid options (Audi Q5) already captured in the
system”— and the report had no way to support OR contradict it.

⚠️ THIS IS NOT A VERDICT. Naming three out of five in one sentence may be sensible conversation, and rattling off five cars
at once may be worse. This provides the NUMBER so the pattern can be seen across many rounds instead of
being debated over a single one — the lesson that cost two mistakes the previous day.
"""
from tests.use_cases.e2e.agent import verify as V

_HOJA = {"n_named": 5, "titles": ["MINI Cooper F55 5p 2016 - GARANTÍA", "FIAT Panda 4x4 diesel",
                                  "Peugeot 3008 2010", "Audi Q5 2015 ETIQUETA C 2.0TDI MANUAL",
                                  "Peugeot 5008 2.0HDI"]}
_DICHO = {"n": 3, "names": ["MINI Cooper F55 5p 2016", "FIAT Panda 4x4 diesel", "Peugeot 3008 2010"]}


def test_el_caso_MEDIDO_sale_con_su_numero():
    """Rewritten 2026-08-28, NOT flipped: the measured number (3 out of 5 = 60%) and the two it missed are the
    same: in that round the sheet had five rows and the prompt included all five, so the two
    names match and the measurement does not change. What changed is that the dict now contains `in_sheet` and
    `shown_to_model` (node 10.105), and EXACT dictionary equality breaks the test every time a field is added
    — without saying anything about what this test protects. The measured values are checked, field by field."""
    r = V.delivery_completeness(_DICHO, _HOJA)
    assert r["named"] == 3 and r["available"] == 5 and r["pct"] == 60
    assert r["missed"] == ["Audi Q5 2015 ETIQUETA C 2.0TDI MANUAL", "Peugeot 5008 2.0HDI"]
    assert r["in_sheet"] == 5, "la hoja de aquella ronda: las dos denominaciones eran la misma"


def test_NOMBRA_las_que_se_dejó():
    """A percentage without saying WHICH ONES forces the entire round to be reconstructed in order to discuss it."""
    assert "Audi Q5" in V.delivery_completeness(_DICHO, _HOJA)["missed"][0]


def test_entregarlo_todo_da_cien():
    r = V.delivery_completeness({"n": 5, "names": _HOJA["titles"]}, _HOJA)
    assert r["pct"] == 100 and r["missed"] == []


def test_sin_hoja_no_hay_porcentaje_que_calcular():
    """And `pct=None`, not 0: it is not that it delivered none of what it had; it had nothing. A zero here
    would accuse the product over a round in which the sheet was never populated."""
    r = V.delivery_completeness({"n": 0, "names": []}, {"n_named": 0, "titles": []})
    assert r["pct"] is None and r["available"] == 0


def test_no_pasa_del_cien_por_ciento():
    """The notes may provide names that are not in the sheet; the percentage is capped."""
    r = V.delivery_completeness({"n": 9, "names": ["x"] * 9}, _HOJA)
    assert r["pct"] == 100


def test_el_informe_LO_LLEVA():
    import inspect

    from tests.use_cases.e2e.agent import run as R
    assert 'mech["delivery_completeness"] = verifymod.delivery_completeness(' in inspect.getsource(R._run_scenario)
