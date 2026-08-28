"""Un `click` contra un elemento muerto no decía qué hacer; su hermano sí, desde siempre.

Medido el 2026-08-28 en el plató 24/7: **siete** «Element is not attached to the DOM» en dos rondas
(`two-searches-two-sheets` y `compare-broadband-plans__es`), con el worker repitiendo `click 13` una y otra
vez. El mensaje era el crudo de Playwright y nada más.

Y la asimetría no tenía motivo: el error del ref fuera de la mirada dice desde siempre *«Haz `look` para verla
otra vez y usa uno de esos números; no inventes refs ni reintentes el mismo»*. Son el mismo problema —un ref
que caducó— contado de dos maneras, y solo una servía.

El mensaje crudo se CONSERVA: es cierto y le sirve a quien depura. Lo que se añade es la salida.
"""
from __future__ import annotations

from nucleo.nav_cli import _salida


def test_el_elemento_muerto_dice_que_mirar_otra_vez():
    s = _salida("Error: ElementHandle.click: Element is not attached to the DOM")
    assert "look" in s and "NUEVO" in s
    assert "repetir el mismo" in s.lower(), "sin esto el worker reintenta, que es lo que hizo siete veces"


def test_el_desplegable_que_no_lo_es_dice_como_se_abre():
    """Medido en la misma tanda: `select_option 40 Recommended` sobre un div que parece un `<select>`."""
    s = _salida("ElementHandle.select_option: Error: Element is not a <select> element")
    assert "click" in s and "look" in s


def test_lo_que_YA_dice_qué_hacer_no_se_duplica():
    """El timeout del navegador y el ref fuera de la mirada ya traen su salida escrita. Añadirles otra encima
    haría el mensaje más largo y menos leído — y una línea que se repite deja de leerse."""
    assert _salida("el navegador no ha contestado a «click» en 25s") == ""
    assert _salida("ref 30 no está en la mirada actual, que tiene 1..8") == ""


def test_un_error_DESCONOCIDO_no_se_inventa_una_salida():
    """La mitad de sensibilidad: sugerir un remedio equivocado es peor que no sugerir ninguno."""
    assert _salida("Exit code 1 · ENOSPC: no space left on device") == ""
    assert _salida("") == ""


def test_el_mensaje_CRUDO_se_conserva():
    """Quien depura necesita el texto de Playwright tal cual; el worker necesita la salida. Los dos caben."""
    import io, contextlib
    from nucleo.nav_cli import _print_state
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        _print_state({"ok": False, "error": "Error: ElementHandle.click: Element is not attached to the DOM"})
    out = buf.getvalue()
    assert "not attached to the DOM" in out and "look" in out
