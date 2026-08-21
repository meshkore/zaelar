"""Una píldora escrita por un cron de widget no es un hecho sobre la persona (V2-242).

Medido por el arnés el 2026-08-21 en `best-plumber-same-day`. En memoria había las dos cosas:

    [long/profile] slot='operator.location' → «Vive en el centro de Madrid.»
    [mid/note]     slot='weather:soria'     → «Weather in Soria now: 14.5C, parcialmente nublado…»

y el worker buscó **«fontanero Soria ciudad urgencias 24 horas»**, tres veces seguidas. El personaje dice Madrid
y NUNCA menciona Soria. La píldora la escribe cada hora `widgets/meteo-soria`, que **viaja TRACKED en el repo
público**: no es memoria sucia de un test, es la que tiene cualquiera que clone.

memoria-dev cerró la mitad de la LECTURA (`memory_agent.compose_context`, 39e68a7): un slot con namespace no
entra en el dosier del operador salvo que la tarea lo nombre. Esto cierra la mitad de la ESCRITURA, que es la que
convierte esa convención en un candado: los lectores separan «hechos del operador» de «píldoras de fondo` **por
la FORMA DE LA CLAVE** —puntos para la persona, namespace para el fondo— y nada impedía que un tick escribiera
`operator.location`, ni que una nota SIN slot cayera bajo «LO QUE SABES DEL OPERADOR». Una convención sin candado
es una promesa.

Namespacear en la CLAVE y no en `meta['widget']` es decisión medida de memoria-dev: **el retriever no devuelve
meta**, así que resolverlo por ahí obligaría a sacar otra columna y a que cada consumidor parseara JSON. Probó
esta forma exacta: `meteo-soria:weather:soria` fuera de «busca un fontanero», dentro de «el tiempo en Soria».
"""
import pytest

from widgets.background import TickCtx


@pytest.mark.parametrize("pedido,esperado", [
    ("weather:soria", "meteo-soria:weather:soria"),      # la forma que memoria-dev probó
    ("estado", "meteo-soria:estado"),                    # sin namespace: se le pone
    (None, "meteo-soria:note"),                          # SIN slot tampoco lo filtra nadie
    ("", "meteo-soria:note"),
    ("meteo-soria:weather:soria", "meteo-soria:weather:soria"),   # ya suya: no se dobla
])
def test_la_pildora_lleva_el_nombre_de_quien_la_escribe(pedido, esperado):
    assert TickCtx("meteo-soria")._own_slot(pedido) == esperado


def test_un_widget_NO_puede_escribir_un_hecho_del_OPERADOR():
    """El caso que la convención dejaba abierto: un tick escribiendo en el espacio de la persona. Con puntos y sin
    namespace, el dosier lo entrega bajo «LO QUE SABES DEL OPERADOR» — un widget podría afirmar dónde vive."""
    out = TickCtx("meteo-soria")._own_slot("operator.location")
    assert out == "meteo-soria:operator.location"
    assert ":" in out, "sin namespace, el lector no puede distinguirlo de un hecho de la persona"


def test_el_namespace_es_el_ID_DEL_WIDGET_y_no_uno_cualquiera():
    """Si dos widgets pudieran compartir namespace, el supersede de uno borraría la píldora del otro."""
    assert TickCtx("meteo-tarragona-grafico")._own_slot("weather:tarragona") \
        == "meteo-tarragona-grafico:weather:tarragona"
    assert TickCtx("meteo-soria")._own_slot("weather:tarragona") == "meteo-soria:weather:tarragona"


def test_lo_que_ESCRIBE_de_verdad_va_namespaceado(monkeypatch):
    """GUARDA DE CABLEADO (V2-199): el predicado puede estar perfecto y `remember` seguir pasando el slot crudo.
    Esto recorre la escritura real hasta `memory.write`."""
    visto = {}

    from memory import api as memory
    monkeypatch.setattr(memory, "write", lambda text, **kw: visto.update(kw, text=text), raising=False)
    TickCtx("meteo-soria").remember("Weather in Soria now: 14.5C.", slot="weather:soria",
                                    kind="note", importance=0.3)
    assert visto.get("slot") == "meteo-soria:weather:soria"
    assert visto.get("meta", {}).get("widget") == "meteo-soria"


def test_un_fallo_al_escribir_no_tumba_el_tick(monkeypatch):
    """Corre dentro del planificador de fondo: una excepción aquí se lleva por delante el ciclo del widget."""
    from memory import api as memory
    monkeypatch.setattr(memory, "write", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bd caída")),
                        raising=False)
    TickCtx("meteo-soria").remember("x", slot="weather:soria")
