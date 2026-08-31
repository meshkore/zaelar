"""Naming the right candidate and attaching an invented amount to it is worse than not naming it.

Measured in `compare-broadband-plans__es` (2026-08-28, 24/7 studio). The sheet had
«Digi · 500 Mb + 100 GB + TV → **23 €/mes**», the agent said it CORRECTLY twice —«ya tengo a Digi
(23€/mes)»— and on the third occasion blurted out *«lo de Digi ronda los **4,9 euros** al mes»*. Same candidate,
invented price, contradicting himself within the same conversation.

The judge caught it by eye and made it blocker no. 1; the report had nothing with which to support it **or
contradict it** — just as happened with «¿entregó lo que tenía?» before the cross-check existed.

A wrong price is not a minor detail: anyone who decides to sign up based on that information gets a surprise of twenty
euros a month. And the correct information was right in front of him, so it is not «he did not know».
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
    """Half the sensitivity, and it matters twice as much here: a false positive accuses the product of lying."""
    assert V.prices_that_do_not_match(_z("Digi te sale por 23€/mes, es la más barata"), _HOJA) == []


def test_no_decir_precio_NO_es_decirlo_mal():
    assert V.prices_that_do_not_match(_z("Digi es la que mejor pinta tiene, te paso el precio ahora"),
                                      _HOJA) == []


def test_sin_precio_en_la_HOJA_no_hay_con_que_comparar():
    """If we do not have the amount, what the agent says may come from the page, and we cannot contradict it."""
    hoja = {"titles": ["Digi · 500 Mb"], "prices": [""]}
    assert V.prices_that_do_not_match(_z("Digi ronda los 4,9 euros"), hoja) == []


def test_un_importe_SUELTO_en_la_frase_no_cuenta():
    """The window comes AFTER the name: «tengo 40€ de presupuesto, y está Digi» does not attach 40 to Digi."""
    assert V.prices_that_do_not_match(_z("me dijiste 40 € de tope; dentro de eso está Digi"), _HOJA) == []


def test_dos_importes_y_uno_CUADRA_no_se_marca():
    """«29,90, rebajado desde 35» contains two numbers, and the correct one is one of them."""
    assert V.prices_that_do_not_match(_z("MásMóvil está a 29,90 €/mes, rebajado desde 35 €"), _HOJA) == []


def test_las_dos_convenciones_de_numero_se_leen_igual():
    """The studio measures in Spanish and English. Choosing only one turns «$1,299.50» into 1,29."""
    assert V._importe("$1,299.50") == 1299.5
    assert V._importe("1.299,50 €") == 1299.5
    assert V._importe("34,99€") == 34.99
    assert V._importe("sin precio") is None


def test_el_ancla_de_precio_NO_es_la_del_detector_de_flips():
    """`_title_head` requires two words and discards generic text because it accuses someone of KNOWING something. Here we are not
    accusing anyone of knowing anything; we are comparing an amount — and with its threshold, `Digi · 500 Mb…` has no anchor, so the
    measured case would not have been caught."""
    assert V._title_head("Digi · 500 Mb + 100 GB + TV") == ""
    assert V._price_anchor("Digi · 500 Mb + 100 GB + TV") == "digi"


def test_llega_al_INFORME_y_al_JUEZ():
    """The plumbing: a detector that is not wired in is a detector that does not exist."""
    from pathlib import Path
    run_src = Path("tests/use_cases/e2e/agent/run.py").read_text(encoding="utf-8")
    judge_src = Path("tests/use_cases/e2e/agent/judge.py").read_text(encoding="utf-8")
    assert 'mech["price_mismatches"] = verifymod.prices_that_do_not_match(' in run_src
    assert 'mech.get("price_mismatches")' in judge_src and "PRECIO EQUIVOCADO" in judge_src


def test_un_titulo_con_ACENTO_no_se_escapa():
    """Caught by taking it apart: the anchor comes from `_norm_title` (without accents) and was searched for in the raw text, so
    «masmovil» NEVER appeared inside «MásMóvil». Two tests in this file were passing because of that
    and not because of the logic — an accented title was invisible to the detector as a whole."""
    got = V.prices_that_do_not_match(_z("MásMóvil te sale por 12 €/mes"), _HOJA)
    assert len(got) == 1 and got[0]["dicho"] == 12.0 and got[0]["en_la_hoja"] == 29.9


def test_el_plegado_conserva_la_LONGITUD():
    """And that is why `_norm_title` is not suitable for this: it collapses punctuation («29,90» → «29 90»), shifts all the
    positions, and also destroys the amount itself, which will be read afterward."""
    a = "MásMóvil está a 29,90 €/mes"
    assert len(V._fold(a)) == len(a)
    assert V._fold(a).startswith("masmovil esta a 29,90")
    assert len(V._norm_title(a)) != len(a), "si esto cambiara, el comentario de arriba dejaría de ser cierto"


def test_se_miran_TODAS_las_menciones_del_nombre_en_un_turno():
    """Caught by comparing against the REAL report, not the fixture. In the «4,9» turn, the word
    «Digi» appears twice and the FIRST occurrence has no price after it («…de Digi; de Movistar y Vodafone aún no me ha
    llegado el dato…»), so keeping that one made precisely the case that motivated all this invisible.

    My synthetic fixture had a single mention and passed green. The real data did not.
    """
    turno = ("Mira, ahora mismo solo tengo confirmado lo de Digi; de Movistar y Vodafone aún no me ha "
             "llegado el dato del precio, así que no te lo puedo dar todavía. Si quieres te lo paso, y "
             "mientras tanto te digo que lo de Digi ronda los 4,9 euros al mes.")
    got = V.prices_that_do_not_match(_z(turno), _HOJA)
    assert len(got) == 1 and got[0]["dicho"] == 4.9


def test_un_ancla_que_vale_para_DOS_filas_no_identifica_a_ninguna():
    """The `search-buy-used-car` sheet contained two Passats: «volkswagen» matched both, and the
    price the agent gave for one was compared with the other's. That is not saying the price incorrectly — it is that we do not know which one
    he was talking about, and accusing him for that is worse than not checking."""
    hoja = {"titles": ["Volkswagen Passat Variant Executive", "Volkswagen Passat 2.0 TDI 2006"],
            "prices": ["24.900 €", "4.999 €"]}
    assert V.prices_that_do_not_match(_z("el Volkswagen Passat sale por 4.999 €"), hoja) == []


def test_un_REDONDEO_al_hablar_no_es_una_mentira():
    """«Ronda los 200» for 205 is how a person speaks. The 5% cutoff separates it from «4,9 sobre 23», and
    came from looking at the 70 mismatches in the sweep: all the roundings fell below it."""
    hoja = {"titles": ["Canon EOS 4000D · kit 18-55"], "prices": ["205 €"]}
    assert V.prices_that_do_not_match(_z("la Canon EOS 4000D ronda los 200 €"), hoja) == []
    assert V.prices_that_do_not_match(_z("la Canon EOS 4000D está a 140 €"), hoja) != []


def test_el_punto_de_MILLAR_no_es_un_decimal():
    """«4.999 €» is four thousand nine hundred ninety-nine. Reading it as 4.999 accused the agent
    of lying when he had stated the price CORRECTLY — measured in the sweep of the 61 saved rounds."""
    assert V._importe("4.999 €") == 4999.0
    assert V._importe("24.900 €") == 24900.0
    assert V._importe("29,90 €") == 29.9, "y el decimal con coma sigue siendo decimal"


def test_una_ETIQUETA_de_anuncio_no_es_el_nombre_de_un_candidato():
    """The sheet includes titles such as «Buen precio» or «Opción i/v · 09:25». Anchoring on «buen» or «opcion» causes
    any sentence containing that word to pull in the amount that follows it."""
    assert V._price_anchor("Buen precio") == ""
    assert V._price_anchor("Opción i/v · 09:25") == ""
    assert V._price_anchor("Nikon D5500") == "nikon"
