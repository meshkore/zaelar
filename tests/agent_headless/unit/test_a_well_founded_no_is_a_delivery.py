"""Searching thoroughly and finding that something does NOT exist is a complete result, but the prompt did not say so.

Measured on `find-concert-tickets__es` (2026-08-28, 24/7 set, `deepseek-v4-flash` brain). There was no Rosalía
concert in Madrid that month — a **complete and correct** answer—yet the worker filled the sheet with events that
were not it, leaving the person waiting for **seven minutes**. The judge: *«does not close with the negative result as
the main conclusion and instead fills the sheet with irrelevant events»*.

The method already covered «I cannot certify it» (step 7). This is **the opposite**, and it was missing: I did certify
it, and what I certified is that it does not exist. Without saying so, the only ending left to the worker is to keep
searching — returning empty-handed is not in its repertoire, so it fills the sheet.
"""
from __future__ import annotations

from nucleo import dispatch_prompts as DP


def _metodo() -> str:
    return DP._method_block("/x/.venv/bin/python") if hasattr(DP, "_method_block") else _buscar_metodo()


def _buscar_metodo() -> str:
    """The method block, regardless of which function currently composes it."""
    import inspect
    src = inspect.getsource(DP)
    i = src.index("7) VERIFICA antes de cerrar")
    return src[i - 4000: i + 4000]


def test_el_no_se_declara_una_ENTREGA():
    t = _buscar_metodo()
    assert "SI LA RESPUESTA ES QUE NO HAY, ESO ES LA ENTREGA" in t


def test_y_se_dice_QUE_hay_que_contar_con_el():
    """A «no» without saying where you looked is not verifiable, and the reader cannot distinguish it from not having
    tried — exactly the uncertainty this product must eliminate."""
    t = _buscar_metodo()
    i = t.index("ESO ES LA ENTREGA")
    assert "dónde miraste" in t[i:i + 400] and "descartaste" in t[i:i + 400]


def test_y_se_PROHÍBE_rellenar():
    """This is the half that keeps the rule from being read as «just say no»: what is prohibited is what it did."""
    t = _buscar_metodo()
    i = t.index("ESO ES LA ENTREGA")
    assert "rellenar con lo que no cumple" in t[i:i + 500]


def test_no_pisa_el_paso_7():
    """«I cannot certify it» and «I have certified that it does not exist» are distinct, and both must remain: the
    former is a limitation; the latter is an answer."""
    t = _buscar_metodo()
    assert "si no se puede certificar, dilo con honestidad" in t
    assert t.index("si no se puede certificar") < t.index("ESO ES LA ENTREGA")
