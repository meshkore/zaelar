"""Nombrar el candidato bueno y colgarle un importe inventado es peor que no nombrarlo.

Medido en `compare-broadband-plans__es` (2026-08-28, plató 24/7). La hoja tenía
«Digi · 500 Mb + 100 GB + TV → **23 €/mes**», el agente lo dijo BIEN dos veces —«ya tengo a Digi
(23€/mes)»— y a la tercera soltó *«lo de Digi ronda los **4,9 euros** al mes»*. Mismo candidato, precio
inventado, contradiciéndose a sí mismo dentro de la misma conversación.

El juez lo cazó a ojo y lo puso de bloqueador nº1; el informe no tenía con qué respaldarlo **ni
contradecirlo** — igual que pasaba con «¿entregó lo que tenía?» antes de que existiera el cruce.

Un precio equivocado no es un matiz: quien decide contratar con ese dato se lleva una sorpresa de veinte
euros al mes. Y el dato bueno lo tenía delante, así que no es «no lo sabía».
"""
from __future__ import annotations

from tests.use_cases.e2e.agent import verify as V

_HOJA = {"titles": ["Digi · 500 Mb + 100 GB + TV", "MásMóvil · fibra + móvil"],
         "prices": ["23 €/mes", "29,90 €/mes"]}


def _z(*textos):
    return [{"who": "zaelar", "text": t} for t in textos]


def test_el_caso_MEDIDO_sale_con_sus_dos_numeros():
    got = V.prices_that_do_not_match(
        _z("ya tengo a Digi (23€/mes) y Pepephone", "lo de Digi ronda los 4,9 euros al mes"), _HOJA)
    assert len(got) == 1
    assert got[0]["en_la_hoja"] == 23.0 and got[0]["dicho"] == 4.9 and got[0]["turno"] == 1


def test_decirlo_BIEN_no_se_marca():
    """La mitad de sensibilidad, y aquí pesa el doble: un falso positivo acusa al producto de mentir."""
    assert V.prices_that_do_not_match(_z("Digi te sale por 23€/mes, es la más barata"), _HOJA) == []


def test_no_decir_precio_NO_es_decirlo_mal():
    assert V.prices_that_do_not_match(_z("Digi es la que mejor pinta tiene, te paso el precio ahora"),
                                      _HOJA) == []


def test_sin_precio_en_la_HOJA_no_hay_con_que_comparar():
    """Si no tenemos el importe, el que diga el agente puede venir de la página y no podemos contradecirlo."""
    hoja = {"titles": ["Digi · 500 Mb"], "prices": [""]}
    assert V.prices_that_do_not_match(_z("Digi ronda los 4,9 euros"), hoja) == []


def test_un_importe_SUELTO_en_la_frase_no_cuenta():
    """La ventana va DETRÁS del nombre: «tengo 40€ de presupuesto, y está Digi» no le cuelga 40 a Digi."""
    assert V.prices_that_do_not_match(_z("me dijiste 40 € de tope; dentro de eso está Digi"), _HOJA) == []


def test_dos_importes_y_uno_CUADRA_no_se_marca():
    """«29,90, rebajado desde 35» lleva dos números y el bueno es uno de ellos."""
    assert V.prices_that_do_not_match(_z("MásMóvil está a 29,90 €/mes, rebajado desde 35 €"), _HOJA) == []


def test_las_dos_convenciones_de_numero_se_leen_igual():
    """El plató mide en castellano y en inglés. Elegir una sola convierte «$1,299.50» en 1,29."""
    assert V._importe("$1,299.50") == 1299.5
    assert V._importe("1.299,50 €") == 1299.5
    assert V._importe("34,99€") == 34.99
    assert V._importe("sin precio") is None


def test_el_ancla_de_precio_NO_es_la_del_detector_de_flips():
    """`_title_head` exige dos palabras y descarta lo genérico porque acusa a alguien de SABER algo. Aquí no
    se acusa de saber nada, se compara un importe — y con su listón, `Digi · 500 Mb…` no tiene ancla y el
    caso medido no se habría cazado."""
    assert V._title_head("Digi · 500 Mb + 100 GB + TV") == ""
    assert V._price_anchor("Digi · 500 Mb + 100 GB + TV") == "digi"


def test_llega_al_INFORME_y_al_JUEZ():
    """La fontanería: un detector que no se cablea es un detector que no existe."""
    from pathlib import Path
    run_src = Path("tests/use_cases/e2e/agent/run.py").read_text(encoding="utf-8")
    judge_src = Path("tests/use_cases/e2e/agent/judge.py").read_text(encoding="utf-8")
    assert 'mech["price_mismatches"] = verifymod.prices_that_do_not_match(' in run_src
    assert 'mech.get("price_mismatches")' in judge_src and "PRECIO EQUIVOCADO" in judge_src


def test_un_titulo_con_ACENTO_no_se_escapa():
    """Cazado desarmando: el ancla sale de `_norm_title` (sin acentos) y se buscaba sobre el texto crudo, así
    que «masmovil» no aparecía JAMÁS dentro de «MásMóvil». Dos tests de este fichero estaban pasando por eso
    y no por la lógica — un título acentuado era invisible para el detector entero."""
    got = V.prices_that_do_not_match(_z("MásMóvil te sale por 12 €/mes"), _HOJA)
    assert len(got) == 1 and got[0]["dicho"] == 12.0 and got[0]["en_la_hoja"] == 29.9


def test_el_plegado_conserva_la_LONGITUD():
    """Y por eso no vale `_norm_title` para esto: colapsa la puntuación («29,90» → «29 90»), mueve todas las
    posiciones y además destroza el propio importe que se va a leer después."""
    a = "MásMóvil está a 29,90 €/mes"
    assert len(V._fold(a)) == len(a)
    assert V._fold(a).startswith("masmovil esta a 29,90")
    assert len(V._norm_title(a)) != len(a), "si esto cambiara, el comentario de arriba dejaría de ser cierto"
