"""«10 propuestas en la hoja de resultados» con la hoja VACÍA, y sin marca ninguna (V2-358).

Medido en `search-buy-used-car` (2026-08-27 08:03, ronda del supervisor, 1/5). A los 60,9 s el anillo de
Proceso pintó esta línea, junto a otras verificadas como «9 resultados en la página» y con la misma letra:

    Preparando entrega: 10 propuestas en la hoja de resultados

La hoja terminó la ronda con **0 filas** (informe de mecanismo: «0 candidato(s) con nombre de 0 fila(s)»). El
operador lee eso, mira su hoja vacía, y las dos cosas no pueden ser verdad — y la que se cree es la que está
escrita con letra de sistema.

Es la misma enfermedad que V2-357 (nombres inventados) una capa más abajo: **algo con forma de hecho que no lo
es**. Y la respuesta es la que ya dio V2-345 para la narración: **no se tira, se MARCA**. El worker AFIRMA
cosas —esta casa pagó que una afirmación suya se tomara por hecho comprobado (V2-249, «Recordatorio
PROGRAMADO» sin poder programar nada)— y en este anillo su prosa convive con lo que sí hemos verificado, así
que tiene que distinguirse a simple vista.

EL CORTE ES ESTRECHO en las dos direcciones, y las dos importan: solo se marca si el paso NOMBRA LA PANTALLA
**y** la hoja está vacía. Un paso mecánico («entrando en coches.net») no se toca — marcarlos todos sería ruido
y acabaría en que nadie mira la marca—, y si la hoja SÍ tiene filas la afirmación es CIERTA y tampoco.

La lista de formas es corta y es de NUESTRO vocabulario —cómo llama el producto a su propia hoja—, no de un
sitio de fuera. Aquí sí sabemos exactamente cómo se nombra, que es justo lo contrario del caso de `dom.py`,
donde una lista de textos estaría condenada porque mañana es otra tienda.
"""
import pytest

from nucleo.flash import live_blocks as LB

HOJA = "results::19e54a-1"
CLAIM = "Preparando entrega: 10 propuestas en la hoja de resultados"


@pytest.fixture
def hoja(monkeypatch):
    """Un mando para decir qué hay en la hoja."""
    from widgets.results import data as _sd
    estado = {"items": []}
    monkeypatch.setattr(_sd, "view_data", lambda sheet, *a, **k: {"items": estado["items"]})
    return estado


def test_la_linea_medida_se_marca(hoja):
    """El caso exacto: afirma diez propuestas sobre una hoja vacía."""
    assert LB.worker_phase_is_a_claim(CLAIM, HOJA) is True


def test_con_la_hoja_LLENA_la_afirmacion_es_cierta_y_no_se_toca(hoja):
    """El lado que importa: marcar algo verdadero enseña al operador a ignorar la marca."""
    hoja["items"] = [{"title": "VOLKSWAGEN Golf Variant 2.0TDI", "price": "11.900 €"}]
    assert LB.worker_phase_is_a_claim(CLAIM, HOJA) is False


def test_un_paso_MECANICO_no_se_marca_nunca(hoja):
    """No habla de la pantalla, así que no afirma nada que el operador pueda desmentir."""
    for p in ("entrando en coches.net", "recorriendo la página", "9 resultados en la página",
              "conduciendo el navegador"):
        assert LB.worker_phase_is_a_claim(p, HOJA) is False, p


def test_filas_SIN_nombre_no_respaldan_nada(hoja):
    """Una hoja con filas huecas está vacía a estos efectos: la misma regla que `by_identity` — una fila sin
    nombre es cromo, no un resultado."""
    hoja["items"] = [{"title": "", "price": "€ 10.475"}, {"title": "   ", "price": "€ 9.900"}]
    assert LB.worker_phase_is_a_claim(CLAIM, HOJA) is True


def test_sin_hoja_resuelta_NO_se_marca(hoja):
    """Marcar por no saber leer sería acusar a ciegas, y el silencio deja el anillo como estaba."""
    assert LB.worker_phase_is_a_claim(CLAIM, "") is False


def test_las_otras_formas_de_nombrar_la_pantalla(hoja):
    for p in ("ya lo tienes en pantalla", "tres opciones en la hoja", "10 rows on screen"):
        assert LB.worker_phase_is_a_claim(p, HOJA) is True, p


def test_una_fase_vacia_no_es_una_afirmacion(hoja):
    assert LB.worker_phase_is_a_claim("", HOJA) is False


def test_el_anillo_lo_CABLEA_y_marca_con_el_mismo_simbolo():
    """Guarda de cableado sobre la fuente sin comentarios: la decisión sin llamante es el arreglo que no
    existe. Y el símbolo es el MISMO que V2-345 — si la narración del worker se marca «💬» y su fase se
    marcara de otra forma, el operador tendría que aprender dos convenciones para el mismo hecho."""
    from pathlib import Path
    src = "\n".join(ln for ln in Path("nucleo/sheets.py").read_text().splitlines()
                    if not ln.strip().startswith("#"))
    i = src.index("def record_phase")
    # Hasta la SIGUIENTE función, no una ventana de N caracteres: el docstring de ésta es largo y un corte
    # fijo dejaba la llamada fuera — la guarda salía roja con el cableado puesto.
    _fin = src.find("\ndef ", i + 10)
    cuerpo = src[i:] if _fin < 0 else src[i:_fin]
    assert "worker_phase_is_a_claim(" in cuerpo, "nadie llama al detector: la marca no puede aparecer nunca"
    assert '"💬 "' in cuerpo, "la marca tiene que ser la misma que la de la narración (V2-345)"
