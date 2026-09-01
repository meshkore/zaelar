"""A stale `ref` said WHAT was happening, but not HOW to get out (V2-248).

The third and last of the causes of a worker dying on its own, among those V2-236 left open
(the other two: the permission gate → V2-241, and `scroll_into_view_if_needed` → V2-247). Measured by the harness on
2026-08-21: `ref 26 no existe`, the V2-212 form.

The message was `ref 26 no existe en el snapshot actual`. It is true and useless: it does not say how many refs there are, or whether
the page has changed, or —above all— that the way out is one command away (`look`). It is the same contract as node
4.20 and V2-203: **what the bridge knows, it SAYS, and a failure also says how to get out of it.**

And what is deliberately NOT done: **retrying with only the new view**. Ref numbers are ASSIGNED when looking,
so 26 in the new view is a different element. Retrying would mean clicking something else — and on a page with
a pay button, clicking something else is exactly what the confirm gate exists to prevent.
"""
import pytest

from widgets.navegador.owner import _stale_ref_reason

URL = "https://tienda.invalid/monitores"


def test_dice_QUE_refs_hay_de_verdad():
    out = _stale_ref_reason(26, {1: 1, 2: 1, 14: 1}, URL, URL)
    assert "1..14" in out, "sin el rango, el worker no sabe si se pasó por uno o por veinte"
    assert "look" in out


def test_si_la_pagina_CAMBIO_lo_dice_y_no_culpa_al_numero():
    out = _stale_ref_reason(26, {1: 1}, URL, "https://tienda.invalid/carrito")
    assert "otra página" in out
    assert "tienda.invalid/carrito" in out
    assert "look" in out


def test_sin_haber_mirado_NUNCA_se_dice_eso_y_no_un_rango_vacio():
    out = _stale_ref_reason(3, {}, "", "")
    assert "todavía no has mirado" in out
    assert ".." not in out, "un rango inventado sobre cero refs manda a buscar algo que no existe"


def test_prohibe_EXPRESAMENTE_reintentar_el_mismo():
    """The model's natural reaction to a failure is to repeat. Here, repeating can never work."""
    out = _stale_ref_reason(26, {1: 1, 9: 1}, URL, URL)
    assert "no inventes refs" in out and "reintentes" in out


def test_un_solo_ref_no_se_anuncia_como_rango():
    assert "1..1" not in _stale_ref_reason(4, {1: 1}, URL, URL)


def test_no_se_reintenta_SOLO_con_la_mirada_nueva():
    """SOURCE GUARD, and it matters more than usual here: retrying with the new snapshot seems like the obvious
    improvement and is a SECURITY failure — numbers are assigned when looking, so the same number is a different
    element. On a page with a pay button, that means clicking something else."""
    import inspect

    from widgets.navegador import owner
    src = inspect.getsource(owner.TaskBrowser)
    assert "_stale_ref_reason(" in src
    # 2026-09-01: the concurrent i18n pass translated this comment (correctly — comments are English in
    # this repo). The guard follows the WORDING, because what it protects is that the reasoning stays
    # written down next to the code that must not be "improved" into a retry.
    assert "Retrying would click something else" in src


@pytest.mark.parametrize("ref", [0, -1, 9999])
def test_cualquier_numero_raro_recibe_una_salida_igual(ref):
    out = _stale_ref_reason(ref, {2: 1, 3: 1}, URL, URL)
    assert "look" in out and str(ref) in out
