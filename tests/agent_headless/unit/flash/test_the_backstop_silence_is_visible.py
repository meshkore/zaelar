"""V2-336 — un backstop que CALLA es indistinguible de uno que decidió callar, y eso costó una ronda entera.

En la ronda limpia del coche (`search-buy-used-car__es`, 2026-08-26 01:06-01:14) hubo tres respuestas de pura
espera con la hoja llevando cinco coches bajo presupuesto, y el backstop de entrega (V2-305) no disparó NI UNA
VEZ — mientras pasaba sus tests unitarios con esas mismas entradas. Todo el bloque vive bajo un `except`
general, así que la avería interna, la que sea, desaparece sin ruido.

Este cambio no arregla el backstop: hace VISIBLE su silencio, emitiendo las ENTRADAS de la decisión.

Y PAGÓ A LA PRIMERA. La ronda siguiente (12:08:59 y 12:09:57) trajo `rows=3` con el backstop callado — o sea
que había filas y aun así no disparaba. Eso llevó a la causa (una guarda mía leía «marcas distintas» como
feed) y a V2-339. Sin el evento, el silencio habría seguido leyéndose como «el modelo retiene resultados».

⚠️ Desde V2-340 esto se prueba por CONDUCTA y no por grep de la fuente: la lógica vive en
`delivery.apply_to_reply`, que recibe la respuesta y la ventana. Un guarda de fuente daba verde con la llamada
presente y el emit roto.
"""
from unittest import mock

from nucleo.flash import delivery as D


def _capturar(monkeypatch, spoken, filas, encargo="busca un coche de segunda mano", dicho=""):
    """Corre el backstop de verdad, con `any_live_task_rows` fijado, y devuelve lo que se emitió."""
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
    """La ronda del 12:09: había TRES filas y el backstop calló porque ya estaban dichas. El evento tiene que
    llevar el 3 — es el número que resolvió el misterio."""
    filas = ["Fiat Panda 4x4 — 6900 €", "Mercedes Clase A — 9500 €", "Peugeot 3008 — 8490 €"]
    dicho = "Ya te dije: el Fiat Panda 4x4, el Mercedes Clase A y el Peugeot 3008."
    _, ev = _capturar(monkeypatch, "te aviso en cuanto lo tenga", filas, dicho=dicho)
    assert ev and ev[0][1]["rows"] == 3
    assert ev[0][1]["said_chars"] > 0


def test_cuando_SÍ_dispara_no_emite_silencio_y_añade_las_filas(monkeypatch):
    filas = ["Fiat Panda 4x4 — 6900 €", "Mercedes Clase A — 9500 €", "Peugeot 3008 — 8490 €"]
    salida, ev = _capturar(monkeypatch, "te aviso en cuanto lo tenga", filas)
    assert "Fiat Panda" in salida, "el backstop no entregó"
    assert ev and "📬" in ev[0][0] and "CALLÓ" not in ev[0][0]


def test_un_turno_NORMAL_no_emite_nada(monkeypatch):
    """Sin esta puerta el evento sería ruido en cada turno en vez de señal."""
    _, ev = _capturar(monkeypatch, "¿Prefieres diésel o gasolina?", [])
    assert ev == []


def test_no_puede_TUMBAR_el_turno(monkeypatch):
    """Fail-soft: si la lectura de filas revienta, la respuesta sale intacta."""
    def _boom():
        raise RuntimeError("registro caído")
    with mock.patch("nucleo.flash.live_blocks.any_live_task_rows", side_effect=_boom):
        assert D.apply_to_reply("Sigo con ello, te aviso.", []) == "Sigo con ello, te aviso."


def test_el_PROBE_lo_llama():
    """La mitad de cableado: la función puede ser perfecta y no tener llamante (V2-199)."""
    from pathlib import Path
    src = "\n".join(ln for ln in Path("nucleo/flash/probe.py").read_text().splitlines()
                    if not ln.strip().startswith("#"))
    assert "apply_to_reply(spoken" in src
