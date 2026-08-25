"""V2-294 — una página a medio cargar devuelve filas HUECAS, y eso no es «sin resultados».

Medido en la tanda del 2026-08-24 13:57, `search-secondhand-monitor__es`. Tres segundos después de navegar al
listado con el filtro ya puesto, la extracción devolvió:

    [ { "title": "", "price": "0 €", "tel": "", "url": "https://es.wallapop.com/item/monitor-1043173153", … } … ]

Son las tarjetas ESQUELETO que un listado pinta mientras hidrata: el enlace ya está, el resto en blanco. El
worker lo diagnosticó él solo —«la extracción devuelve datos pobres (títulos vacíos, precios en 0)»— y gastó dos
vueltas en recuperarse; la siguiente extracción, **sobre la misma página**, trajo monitores reales con precio. En
`search-buy-bicycle__es` y `search-buy-guitar__es` la ronda se acabó antes de que se recuperara: `extr=0` tres
tandas seguidas.

La señal para mirar otra vez es inequívoca y no necesita saber de qué sitio se trata: **hay filas y NINGUNA tiene
identidad**. Con CERO filas no se reintenta —eso sí puede ser una página sin resultados, y hacer esperar dos
segundos a cada búsqueda vacía es que paguen todas para arreglar unas pocas— y solo UNA vez, porque a la segunda
ya no es que esté cargando.
"""
import asyncio

import pytest

from widgets.navegador import act_api

_HUECAS = [{"title": "", "price": "0 €", "url": "https://es.wallapop.com/item/monitor-1043173153"},
           {"title": "", "price": "0 €", "url": "https://es.wallapop.com/item/monitor-1043173154"}]
_REALES = [{"title": "Monitor MSI MAG 276CXF 27 LED Curvo 280Hz", "price": "100 €", "url": "https://x/1"},
           {"title": "Dell UltraSharp U2414H Monitor", "price": "115 €", "url": "https://x/2"}]


class _Tab:
    """Una pestaña que devuelve una lista distinta en cada extracción, como hace una que está hidratando."""
    def __init__(self, *rondas):
        self.rondas, self.n = list(rondas), 0

    async def ensure(self):
        return None

    async def extract_listings(self, limit):
        out = self.rondas[min(self.n, len(self.rondas) - 1)]
        self.n += 1
        return out

    #: V2-323 añadió una SEGUNDA mirada, la de las páginas que pintan al acercarse, y necesita la página real.
    #: Aquí se declara APAGADA a propósito: estos tests miden la mirada de V2-294 (la hidratación) y sólo esa.
    #: Dejar el atributo fuera no habría sido «no participar» — habría sido un `AttributeError` convertido en
    #: respuesta de error, que es como se descubrió que el contrato de la pestaña había crecido.
    page = None


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    """Sin espera real (el test no mide segundos) y sin tocar hoja, bus ni conversación."""
    monkeypatch.setattr(act_api, "_HYDRATE_WAIT_S", 0)
    monkeypatch.setattr(act_api, "_emit_nav", lambda *a, **k: None)
    monkeypatch.setattr(act_api, "_say_phase", lambda *a, **k: None)
    monkeypatch.setattr(act_api, "_hand_over", lambda *a, **k: None)
    # El empujón de V2-323 se apaga aquí: con una página falsa no hay nada que recorrer, y estos tests miden
    # la mirada de la HIDRATACIÓN. Apagarlo explícitamente es lo que mantiene a cada test midiendo UNA cosa.
    async def _sin_empujon(_page):
        return False
    monkeypatch.setattr(act_api._lazy, "materialise_below_the_fold", _sin_empujon)
    yield


def _run(tab, monkeypatch):
    """Por el camino REAL del puente (`navegador_act`), no llamando al predicado a mano: la lección de V2-199 es
    que un test que no recorre el camino prueba que el código compila. Se sustituye SOLO el registro de pestañas,
    que es la frontera con Chromium."""
    from widgets.navegador import owner
    monkeypatch.setitem(owner._task_browsers, "t1", tab)
    return asyncio.run(act_api.navegador_act(task_id="t1", action="extract", args={"limit": 14}))


# ── el predicado, que es donde vive la decisión ───────────────────────────────────────────────────────────
def test_hollow_rows_have_no_identity():
    """La señal: filas con enlace y nada más. `by_identity` ya sabe contestarlo — no hace falta un criterio nuevo."""
    named, unnamed = act_api.by_identity(_HUECAS)
    assert named == [] and len(unnamed) == 2


def test_real_rows_do_have_identity():
    assert len(act_api.by_identity(_REALES)[0]) == 2


# ── y el REINTENTO, por el camino real del puente ─────────────────────────────────────────────────────────
def test_a_hollow_page_is_looked_at_once_more(monkeypatch):
    """EL CASO MEDIDO: primera extracción hueca, segunda con monitores reales."""
    tab = _Tab(_HUECAS, _REALES)
    out = _run(tab, monkeypatch)
    assert tab.n == 2, "no volvió a mirar"
    assert [i["title"] for i in out["listings"]] == [i["title"] for i in _REALES]


def test_a_page_that_is_really_empty_is_not_retried(monkeypatch):
    """Cero filas SÍ puede ser una página sin resultados. Reintentar ahí hace esperar a toda búsqueda vacía."""
    tab = _Tab([], [])
    out = _run(tab, monkeypatch)
    assert tab.n == 1
    assert out["n"] == 0


def test_a_good_page_is_not_looked_at_twice(monkeypatch):
    """Sin esta, «mira otra vez» se satisface mirando siempre dos veces, que dobla el coste de cada extracción."""
    tab = _Tab(_REALES, _REALES)
    out = _run(tab, monkeypatch)
    assert tab.n == 1
    assert out["n"] == 2


def test_it_gives_up_after_one_more_look(monkeypatch):
    """Una página que sigue hueca no está cargando: se entrega lo que hay y el worker decide (cambiar de búsqueda
    o de sitio). Insistir aquí es el bucle que V2-186 vino a cortar."""
    tab = _Tab(_HUECAS, _HUECAS, _REALES)
    out = _run(tab, monkeypatch)
    assert tab.n == 2
    assert [i["title"] for i in out["listings"]] == ["", ""]


def test_the_retry_result_is_only_kept_when_it_is_better(monkeypatch):
    """Si la segunda mirada trae MENOS, quedarse con ella sería empeorar por reintentar."""
    tab = _Tab(_HUECAS, [])
    out = _run(tab, monkeypatch)
    assert out["n"] == 2, "se quedó con la segunda, que traía menos que la primera"
