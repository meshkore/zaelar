"""V2-332 — de las filas que el sistema le puso delante, ¿cuántas llegó a nombrar?

El informe ya sabía qué le dieron (`results_sheet`) y qué dijo (`delivered_by_name`, V2-329/331). Faltaba el
CRUCE, que es la pregunta del operador: no «¿entregó algo?» sino **«¿entregó lo que tenía?»**.

Medido en `search-buy-used-car__es` (2026-08-26 01:14) — la primera ronda del caso con la cadena de extracción
ya arreglada, y por eso la primera en la que esta pregunta tiene sentido. La hoja llevaba cinco coches reales,
todos por debajo del tope de 12.000 €:

    MINI Cooper F55 2016 — 11.700 €   ·   Audi Q5 2015 2.0TDI — 11.990 €
    FIAT Panda 4x4 diesel — 6.900 €   ·   Peugeot 5008 2.0HDI — 6.990 €
    Peugeot 3008 2010 — 3.490 €

y zaelar nombró TRES. El juez lo vio —«ignorar opciones válidas mejores (Audi Q5) ya capturadas en el
sistema»— y el informe no tenía con qué respaldarlo NI contradecirlo.

⚠️ NO ES UN VEREDICTO. Nombrar tres de cinco en una frase puede ser conversación sensata, y soltar cinco coches
de golpe puede ser peor. Esto da el NÚMERO para que el patrón se vea a lo largo de muchas rondas en vez de
discutirse sobre una — la lección que costó dos equivocaciones el día anterior.
"""
from tests.use_cases.e2e.agent import verify as V

_HOJA = {"n_named": 5, "titles": ["MINI Cooper F55 5p 2016 - GARANTÍA", "FIAT Panda 4x4 diesel",
                                  "Peugeot 3008 2010", "Audi Q5 2015 ETIQUETA C 2.0TDI MANUAL",
                                  "Peugeot 5008 2.0HDI"]}
_DICHO = {"n": 3, "names": ["MINI Cooper F55 5p 2016", "FIAT Panda 4x4 diesel", "Peugeot 3008 2010"]}


def test_el_caso_MEDIDO_sale_con_su_numero():
    r = V.delivery_completeness(_DICHO, _HOJA)
    assert r == {"named": 3, "available": 5, "pct": 60,
                 "missed": ["Audi Q5 2015 ETIQUETA C 2.0TDI MANUAL", "Peugeot 5008 2.0HDI"]}


def test_NOMBRA_las_que_se_dejó():
    """Un porcentaje sin decir CUÁLES obliga a reconstruir la ronda entera para poder discutirlo."""
    assert "Audi Q5" in V.delivery_completeness(_DICHO, _HOJA)["missed"][0]


def test_entregarlo_todo_da_cien():
    r = V.delivery_completeness({"n": 5, "names": _HOJA["titles"]}, _HOJA)
    assert r["pct"] == 100 and r["missed"] == []


def test_sin_hoja_no_hay_porcentaje_que_calcular():
    """Y `pct=None`, no 0: no es que entregara nada de lo que tenía, es que no tenía nada. Un cero aquí
    acusaría al producto de una ronda en la que la hoja nunca se llenó."""
    r = V.delivery_completeness({"n": 0, "names": []}, {"n_named": 0, "titles": []})
    assert r["pct"] is None and r["available"] == 0


def test_no_pasa_del_cien_por_ciento():
    """Las notas pueden aportar nombres que no están en la hoja; el porcentaje se acota."""
    r = V.delivery_completeness({"n": 9, "names": ["x"] * 9}, _HOJA)
    assert r["pct"] == 100


def test_el_informe_LO_LLEVA():
    import inspect

    from tests.use_cases.e2e.agent import run as R
    assert 'mech["delivery_completeness"] = verifymod.delivery_completeness(' in inspect.getsource(R._run_scenario)
