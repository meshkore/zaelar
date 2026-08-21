"""Un `ref` caducado decía QUÉ pasaba y no CÓMO salir (V2-248).

Tercera y última de las causas por las que un worker se moría por su cuenta, de las que V2-236 dejó abiertas
(las otras dos: la puerta de permiso → V2-241, y `scroll_into_view_if_needed` → V2-247). Medido por el arnés el
2026-08-21: `ref 26 no existe`, la forma de V2-212.

El mensaje era `ref 26 no existe en el snapshot actual`. Es verdad y no sirve: no dice cuántos refs hay, ni que
la página haya cambiado, ni —sobre todo— que la salida está a un comando (`look`). Es el mismo contrato del nodo
4.20 y de V2-203: **lo que el puente sabe, lo DICE, y un fallo dice además cómo se sale de él.**

Y lo que NO se hace, a propósito: **reintentar solo con la mirada nueva**. Los números de ref se REPARTEN al
mirar, así que el 26 de la mirada nueva es otro elemento. Reintentar sería clicar otra cosa — y en una página con
un botón de pagar, clicar otra cosa es exactamente lo que el confirm-gate existe para impedir.
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
    """La reacción natural del modelo ante un fallo es repetir. Aquí repetir no puede funcionar nunca."""
    out = _stale_ref_reason(26, {1: 1, 9: 1}, URL, URL)
    assert "no inventes refs" in out and "reintentes" in out


def test_un_solo_ref_no_se_anuncia_como_rango():
    assert "1..1" not in _stale_ref_reason(4, {1: 1}, URL, URL)


def test_no_se_reintenta_SOLO_con_la_mirada_nueva():
    """GUARDA DE FUENTE, y aquí importa más que de costumbre: reintentar con el snapshot nuevo parece la mejora
    obvia y es un fallo de SEGURIDAD — los números se reparten al mirar, así que el mismo número es otro
    elemento. En una página con botón de pagar, eso es clicar otra cosa."""
    import inspect

    from widgets.navegador import owner
    src = inspect.getsource(owner.TaskBrowser)
    assert "_stale_ref_reason(" in src
    assert "Reintentar sería clicar otra cosa" in src


@pytest.mark.parametrize("ref", [0, -1, 9999])
def test_cualquier_numero_raro_recibe_una_salida_igual(ref):
    out = _stale_ref_reason(ref, {2: 1, 3: 1}, URL, URL)
    assert "look" in out and str(ref) in out
