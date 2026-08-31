"""A `click` on a dead element did not say what to do; its sibling always did.

Measured on 2026-08-28 in the 24/7 test environment: **seven** «Element is not attached to the DOM» errors in two rounds
(`two-searches-two-sheets` and `compare-broadband-plans__es`), with the worker repeating `click 13` over and over.
The message was Playwright's raw output and nothing more.

And there was no reason for the asymmetry: the error for a ref outside the view has always said *«Use `look` to see it
again and use one of those numbers; do not invent refs or retry the same one»*. They are the same problem—a ref
that expired—described in two ways, and only one was useful.

The raw message is PRESERVED: it is accurate and useful to whoever is debugging. What is added is the guidance.
"""
from __future__ import annotations

from nucleo.nav_cli import _salida


def test_el_elemento_muerto_dice_que_mirar_otra_vez():
    s = _salida("Error: ElementHandle.click: Element is not attached to the DOM")
    assert "look" in s and "NUEVO" in s
    assert "repetir el mismo" in s.lower(), "sin esto el worker reintenta, que es lo que hizo siete veces"


def test_el_desplegable_que_no_lo_es_dice_como_se_abre():
    """Measured in the same run: `select_option 40 Recommended` on a div that looks like a `<select>`."""
    s = _salida("ElementHandle.select_option: Error: Element is not a <select> element")
    assert "click" in s and "look" in s


def test_lo_que_YA_dice_qué_hacer_no_se_duplica():
    """The browser timeout and the ref outside the view already have their guidance written. Adding another on top
    would make the message longer and less readable—and a line that is repeated stops being read."""
    assert _salida("el navegador no ha contestado a «click» en 25s") == ""
    assert _salida("ref 30 no está en la mirada actual, que tiene 1..8") == ""


def test_un_error_DESCONOCIDO_no_se_inventa_una_salida():
    """The sensitivity half: suggesting the wrong remedy is worse than suggesting none."""
    assert _salida("Exit code 1 · ENOSPC: no space left on device") == ""
    assert _salida("") == ""


def test_el_mensaje_CRUDO_se_conserva():
    """Whoever is debugging needs Playwright's text as-is; the worker needs the guidance. Both fit."""
    import io, contextlib
    from nucleo.nav_cli import _print_state
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        _print_state({"ok": False, "error": "Error: ElementHandle.click: Element is not attached to the DOM"})
    out = buf.getvalue()
    assert "not attached to the DOM" in out and "look" in out
