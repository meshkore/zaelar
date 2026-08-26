"""V2-335 — un backstop que CALLA es indistinguible de uno que decidió callar, y eso costó una ronda entera.

En la ronda limpia del coche (`search-buy-used-car__es`, 2026-08-26 01:06-01:14) hubo tres respuestas de pura
espera —una de ellas «Vale, dame un momento que lo miro» ante una nota con TRES coches válidos y la orden
«NÓMBRALO EN ESTE TURNO»— con la hoja llevando cinco coches bajo presupuesto. El backstop de entrega (V2-305)
no disparó NI UNA VEZ en toda la corrida.

Y pasa sus tests unitarios con ESAS MISMAS entradas: frase, filas, ventana y encargo reproducidos uno a uno
disparan en la mano. Todo el bloque vive en un `try/except pass`, así que la avería interna —la que sea—
desaparece sin ruido. La única entrada no reproducible desde fuera es `any_live_task_rows()` dentro del motor
en aquel instante.

Este cambio no arregla el backstop: hace VISIBLE su silencio. Cuando la respuesta es de espera y el backstop
devuelve "", se emite un evento con las ENTRADAS de la decisión (cuántas filas, de qué encargo, cuánto había
dicho la ventana). La próxima ronda que lo sufra deja la respuesta escrita en vez de otro misterio.
"""
import inspect

from nucleo.flash import probe as P


def _src():
    return "\n".join(l for l in inspect.getsource(P).splitlines() if not l.strip().startswith("#"))


def test_el_silencio_emite_con_las_ENTRADAS():
    src = _src()
    i = src.find("backstop de entrega CALLÓ")
    assert i > 0, "el silencio del backstop volvió a ser invisible"
    tramo = src[max(0, i - 600):i + 400]
    for campo in ('"rows"', '"goal"', '"said_chars"', '"reply"'):
        assert campo in tramo, f"el emit no lleva {campo}: sin las entradas no se puede diagnosticar"


def test_solo_ante_una_ESPERA_no_en_cada_turno():
    """Sin esta puerta, cada turno normal emitiría un «calló» y el evento sería ruido en vez de señal."""
    src = _src()
    i = src.find("backstop de entrega CALLÓ")
    assert "_WAITING_REPLY_RE.search" in src[max(0, i - 600):i], \
        "el emit no está gateado a las respuestas de espera"


def test_y_NO_sustituye_al_disparo():
    """Las dos ramas conviven: si el backstop dispara, sale el 📬 de siempre; el 🤐 es solo el else."""
    src = _src()
    assert "📬 backstop de entrega" in src
    assert src.find("📬 backstop de entrega") < src.find("backstop de entrega CALLÓ")
