"""A pill written by a widget cron is not a fact about the person (V2-242).

Measured by the harness on 2026-08-21 in `best-plumber-same-day`. Memory contained both things:

    [long/profile] slot='operator.location' → «Vive en el centro de Madrid.»
    [mid/note]     slot='weather:soria'     → «Weather in Soria now: 14.5C, parcialmente nublado…»

and the worker searched for **«fontanero Soria ciudad urgencias 24 horas»**, three times in a row. The character says Madrid
and NEVER mentions Soria. The pill is written every hour by `widgets/meteo-soria`, which **travels TRACKED in the public
repo**: it is not dirty memory from a test, it is the memory anyone who clones has.

memoria-dev closed half of the READ path (`memory_agent.compose_context`, 39e68a7): a namespaced slot does not
enter the operator dossier unless the task names it. This closes half of the WRITE path, the part that turns that
convention into a lock: readers separate «operator facts» from «background pills» **by the FORM OF THE KEY** —dots
for the person, namespace for the background— and nothing prevented a tick from writing `operator.location`, nor a
note with NO slot from falling under «WHAT YOU KNOW ABOUT THE OPERATOR». A convention without a lock is a promise.

Namespacing in the KEY rather than in `meta['widget']` is a decision measured by memoria-dev: **the retriever does not
return meta**, so resolving it there would require adding another column and having every consumer parse JSON. It
tested this exact form: `meteo-soria:weather:soria` outside «search for a plumber», inside «the weather in Soria».
"""
import pytest

from widgets.background import TickCtx


@pytest.mark.parametrize("pedido,esperado", [
    ("weather:soria", "meteo-soria:weather:soria"),      # the form memoria-dev tested
    ("estado", "meteo-soria:estado"),                    # without a namespace: one is added
    (None, "meteo-soria:note"),                          # even with NO slot does anyone filter it
    ("", "meteo-soria:note"),
    ("meteo-soria:weather:soria", "meteo-soria:weather:soria"),   # already its own: it is not doubled
])
def test_la_pildora_lleva_el_nombre_de_quien_la_escribe(pedido, esperado):
    assert TickCtx("meteo-soria")._own_slot(pedido) == esperado


def test_un_widget_NO_puede_escribir_un_hecho_del_OPERADOR():
    """The case the convention left open: a tick writing in the person's space. With dots and no
    namespace, the dossier delivers it under «WHAT YOU KNOW ABOUT THE OPERATOR» — a widget could assert where they live."""
    out = TickCtx("meteo-soria")._own_slot("operator.location")
    assert out == "meteo-soria:operator.location"
    assert ":" in out, "sin namespace, el lector no puede distinguirlo de un hecho de la persona"


def test_el_namespace_es_el_ID_DEL_WIDGET_y_no_uno_cualquiera():
    """If two widgets could share a namespace, one widget's supersede would erase the other's pill."""
    assert TickCtx("meteo-tarragona-grafico")._own_slot("weather:tarragona") \
        == "meteo-tarragona-grafico:weather:tarragona"
    assert TickCtx("meteo-soria")._own_slot("weather:tarragona") == "meteo-soria:weather:tarragona"


def test_lo_que_ESCRIBE_de_verdad_va_namespaceado(monkeypatch):
    """WIRING GUARD (V2-199): the predicate can be perfect while `remember` continues passing the raw slot.
    This traces the real write all the way to `memory.write`."""
    visto = {}

    from memory import api as memory
    monkeypatch.setattr(memory, "write", lambda text, **kw: visto.update(kw, text=text), raising=False)
    TickCtx("meteo-soria").remember("Weather in Soria now: 14.5C.", slot="weather:soria",
                                    kind="note", importance=0.3)
    assert visto.get("slot") == "meteo-soria:weather:soria"
    assert visto.get("meta", {}).get("widget") == "meteo-soria"


def test_un_fallo_al_escribir_no_tumba_el_tick(monkeypatch):
    """It runs inside the background scheduler: an exception here takes down the widget cycle."""
    from memory import api as memory
    monkeypatch.setattr(memory, "write", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bd caída")),
                        raising=False)
    TickCtx("meteo-soria").remember("x", slot="weather:soria")
