"""56 búsquedas web, 31 consultas, 0 candidatos: eso no es diligencia, es dar vueltas.

Medido en `weekend-plan-barcelona__es` (2026-08-28, plató 24/7). El juez lo escribió con esas palabras:
*«repitiendo la misma consulta sin cambiar de criterio… una petición se piensa, se busca una vez con las
condiciones puestas y se entrega»*. Cada vuelta cuesta segundos del cliente, cuota del proveedor y un turno
de conversación en el que zaelar dice que sigue buscando.

NO se bloquea la repetición, se CONTESTA — y se marca. Bloquear rompería un reintento legítimo; devolver lo
mismo al instante corta el bucle igual, y además deja el hecho escrito (`repeated`), que es lo que convierte
«dio vueltas» de impresión en dato.

El TTL corto (120 s) ES el diseño, no un parámetro suelto: largo para matar un bucle apretado —56 búsquedas
en nueve minutos—, corto para que un «mira otra vez» a ritmo humano traiga mundo fresco. Una caché de
búsqueda que dure más que la paciencia de una persona sirve datos rancios justo a quien pidió lo contrario.
"""
from __future__ import annotations

import pytest

from nucleo import websearch as W


@pytest.fixture(autouse=True)
def _limpio():
    W._recent.clear()
    yield
    W._recent.clear()


def _backend_contador(monkeypatch, veces: list):
    def _b(q, k):
        veces.append(q)
        return {"query": q, "answer": "", "results": [{"title": f"r{len(veces)}", "url": "u", "snippet": ""}],
                "source": "ddg", "ai": False}
    monkeypatch.setattr(W, "_order", lambda: ["ddg"])
    monkeypatch.setitem(W._BACKENDS, "ddg", _b)


def test_la_segunda_vez_no_sale_a_la_red(monkeypatch):
    veces: list = []
    _backend_contador(monkeypatch, veces)
    a = W.search("salas de conciertos barcelona", 5)
    b = W.search("salas de conciertos barcelona", 5)
    assert len(veces) == 1, "la segunda consulta idéntica no puede volver a gastar red"
    assert b["results"] == a["results"]


def test_y_lo_DICE(monkeypatch):
    """Sin la marca, «dio vueltas» sigue siendo una impresión del juez en vez de un dato del informe."""
    veces: list = []
    _backend_contador(monkeypatch, veces)
    W.search("hoteles en sevilla", 5)
    b = W.search("hoteles en sevilla", 5)
    assert b["repeated"]["n"] >= 1 and b["repeated"]["ttl_s"] == 120


def test_la_primera_no_lleva_marca(monkeypatch):
    """La mitad de sensibilidad: una marca que sale siempre deja de ser una marca."""
    _backend_contador(monkeypatch, [])
    assert "repeated" not in W.search("algo nuevo", 5)


def test_dos_consultas_DISTINTAS_son_dos_busquedas(monkeypatch):
    veces: list = []
    _backend_contador(monkeypatch, veces)
    W.search("fontanero madrid", 5)
    W.search("fontanero barcelona", 5)
    assert len(veces) == 2


def test_la_misma_consulta_con_otro_espaciado_o_mayusculas_es_la_misma(monkeypatch):
    veces: list = []
    _backend_contador(monkeypatch, veces)
    W.search("Salas   de Conciertos BARCELONA", 5)
    W.search("salas de conciertos barcelona", 5)
    assert len(veces) == 1


def test_pasado_el_TTL_se_vuelve_a_buscar(monkeypatch):
    """Un «mira otra vez» a ritmo humano tiene que traer mundo fresco."""
    veces: list = []
    _backend_contador(monkeypatch, veces)
    W.search("conciertos este finde", 5)
    ahora = W._time.time()
    monkeypatch.setattr(W._time, "time", lambda: ahora + W._REPEAT_TTL_S + 1)
    W.search("conciertos este finde", 5)
    assert len(veces) == 2


def test_no_se_cobra_dos_veces_por_una_sola_peticion(monkeypatch):
    """`_meter_search` cobra lo que RESPONDIÓ un proveedor. Una respuesta servida de memoria no lo hizo."""
    cobros: list = []
    monkeypatch.setattr(W, "_meter_search", lambda src: cobros.append(src))
    _backend_contador(monkeypatch, [])
    W.search("un seguro barato", 5)
    W.search("un seguro barato", 5)
    assert len(cobros) == 1


def test_esta_acotado(monkeypatch):
    """Vive en el proceso del motor: no es un almacén y no puede crecer sin freno."""
    _backend_contador(monkeypatch, [])
    for i in range(W._REPEAT_MAX + 20):
        W.search(f"consulta numero {i}", 5)
    assert len(W._recent) <= W._REPEAT_MAX
