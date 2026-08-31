"""V2-336 — a backstop that SILENTLY FAILS is indistinguishable from one that decided to stay silent, and that cost an entire round.

In the clean car round (`search-buy-used-car__es`, 2026-08-26 01:06-01:14), there were three pure-wait
responses with the sheet carrying five under-budget cars, and the delivery backstop (V2-305) did not fire ONCE
— while passing its unit tests with those same inputs. The entire block lives under a general `except`,
so whatever the internal failure is, it disappears without a sound.

This change does not fix the backstop: it makes its silence VISIBLE by emitting the decision's INPUTS.

AND IT PAID OFF IMMEDIATELY. The next round (12:08:59 and 12:09:57) brought `rows=3` with the backstop silent
— meaning there were rows and it still did not fire. That led to the cause (one of my guards read “different
marks” as a feed) and to V2-339. Without the event, the silence would have continued to be read as “the model
is withholding results.”

⚠️ Since V2-340 this has been tested by BEHAVIOR rather than by grepping the source: the logic lives in
`delivery.apply_to_reply`, which receives the response and the window. A source guard passed with the call
present and the emit broken.
"""
from unittest import mock

from nucleo.flash import delivery as D


def _capturar(monkeypatch, spoken, filas, encargo="busca un coche de segunda mano", dicho=""):
    """Run the real backstop, with `any_live_task_rows` pinned, and return what was emitted."""
    emitido = []
    monkeypatch.setattr(D, "_emit", lambda label, **extra: emitido.append((label, extra)))
    with mock.patch("nucleo.flash.live_blocks.any_live_task_rows", return_value=(encargo, filas)):
        ventana = [{"role": "assistant", "content": dicho}] if dicho else []
        salida = D.apply_to_reply(spoken, ventana)
    return salida, emitido


def test_una_espera_SIN_filas_emite_el_silencio_con_sus_entradas(monkeypatch):
    salida, ev = _capturar(monkeypatch, "Sigo con ello; te aviso en cuanto lo tenga.", [])
    assert salida == "Sigo con ello; te aviso en cuanto lo tenga.", "no debe tocar la respuesta"
    assert ev and "CALLÓ" in ev[0][0]
    datos = ev[0][1]
    for campo in ("rows", "goal", "said_chars", "reply"):
        assert campo in datos, f"el emit no lleva «{campo}»: sin las entradas no se puede diagnosticar"
    assert datos["rows"] == 0


def test_el_caso_MEDIDO_rows_3_y_calla_queda_registrado(monkeypatch):
    """The 12:09 round: there were THREE rows and the backstop stayed silent because they had already been said. The event must
    carry the 3 — it is the number that solved the mystery."""
    filas = ["Fiat Panda 4x4 — 6900 €", "Mercedes Clase A — 9500 €", "Peugeot 3008 — 8490 €"]
    # name + data: since V2-471, a row with a price only counts as said when its price was also spoken
    dicho = ("Ya te dije: el Fiat Panda 4x4 por 6900 €, el Mercedes Clase A por 9500 € y el "
             "Peugeot 3008 por 8490 €.")
    _, ev = _capturar(monkeypatch, "te aviso en cuanto lo tenga", filas, dicho=dicho)
    assert ev and ev[0][1]["rows"] == 3
    assert ev[0][1]["said_chars"] > 0


def test_cuando_SÍ_dispara_no_emite_silencio_y_añade_las_filas(monkeypatch):
    filas = ["Fiat Panda 4x4 — 6900 €", "Mercedes Clase A — 9500 €", "Peugeot 3008 — 8490 €"]
    salida, ev = _capturar(monkeypatch, "te aviso en cuanto lo tenga", filas)
    assert "Fiat Panda" in salida, "el backstop no entregó"
    assert ev and "📬" in ev[0][0] and "CALLÓ" not in ev[0][0]


def test_un_turno_NORMAL_no_emite_nada(monkeypatch):
    """Without this gate, the event would be noise on every turn instead of a signal."""
    _, ev = _capturar(monkeypatch, "¿Prefieres diésel o gasolina?", [])
    assert ev == []


def test_no_puede_TUMBAR_el_turno(monkeypatch):
    """Fail-soft: if reading the rows blows up, the response comes out intact."""
    def _boom():
        raise RuntimeError("registro caído")
    with mock.patch("nucleo.flash.live_blocks.any_live_task_rows", side_effect=_boom):
        assert D.apply_to_reply("Sigo con ello, te aviso.", []) == "Sigo con ello, te aviso."


def test_el_PROBE_lo_llama():
    """Half the wiring: the function can be perfect and have no caller (V2-199)."""
    from pathlib import Path
    src = "\n".join(ln for ln in Path("nucleo/flash/probe.py").read_text().splitlines()
                    if not ln.strip().startswith("#"))
    assert "apply_to_reply(spoken" in src
