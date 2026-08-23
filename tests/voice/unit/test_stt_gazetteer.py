"""voice/engine/speech/stt/gazetteer.py — el refuerzo de términos del STT remoto.

El caso que lo motivó es real y está medido: Deepgram partió «Calatayud» en «cal»+«a», el segmentador pegó 23
fragmentos y el destilador acabó escribiendo que el operador vive en un sitio donde no vive. Estos tests cubren
las dos mitades que importan: que los nombres que fallaron ESTÁN, y que la lista no puede crecer hasta dejar
el motor sordo — pasarse del tope de Deepgram es un 400 en la petición de escucha, o sea ningún STT.
"""
from __future__ import annotations

import pytest

from voice.engine.core import langs
from voice.engine.speech.stt import deepgram as dg
from voice.engine.speech.stt import gazetteer as gz


@pytest.fixture(autouse=True)
def _sin_cache():
    gz._load.cache_clear()
    yield
    gz._load.cache_clear()


# ── el sobre medido: pasarse es quedarse SORDO ──────────────────────────────────────────────────────────────

def test_la_lista_que_se_publica_cabe_en_el_tope_de_deepgram():
    """El trinquete de verdad. Deepgram cuenta SUB-TOKENS, no entradas, así que no hay forma de contarlo desde
    aquí: lo que se guarda es el sobre que se midió contra la API viva (114 nombres reales / 1221 chars el
    2026-08-23) con margen, porque estos nombres son más raros que los que se bisectaron y cuestan más tokens
    cada uno. Si alguien añade veinte pueblos, este test se pone rojo ANTES de que el operador se quede sin voz."""
    shipped = gz._load("es")
    assert shipped, "sin lista no hay refuerzo — el fichero de datos no se está publicando"
    assert len(shipped) <= gz.MAX_TERMS, f"{len(shipped)} términos supera el tope medido ({gz.MAX_TERMS})"
    assert sum(len(t) for t in shipped) <= gz.MAX_CHARS


def test_el_clamp_recorta_aunque_el_fichero_crezca():
    """Cinturón además de tirantes: el test de arriba guarda el fichero, esto guarda la llamada. Uno de más no
    es un pueblo mal transcrito, es la sesión entera sin transcribir."""
    assert len(gz._clamp([f"Pueblo{i}" for i in range(500)])) <= gz.MAX_TERMS
    assert sum(len(t) for t in gz._clamp(["x" * 100] * 50)) <= gz.MAX_CHARS


def test_un_idioma_sin_lista_no_refuerza_nada():
    assert gz.terms("ja") == []
    assert gz.terms("") == []


# ── que el arreglo LLEGUE al caso que lo motivó ─────────────────────────────────────────────────────────────

def test_los_nombres_que_fallaron_estan_en_la_lista():
    """Sin esto el módulo puede estar perfecto y no servir de nada. Estos dos son los del incidente del
    operador, y son justo los que un criterio por POBLACIÓN habría dejado fuera: Calatayud es el #429 y Valls
    el #321, así que con 114 huecos ninguno entra. Por eso el criterio es el riesgo medido, no el tamaño."""
    shipped = {t.lower() for t in gz._load("es")}
    for nombre in ("calatayud", "valls"):
        assert nombre in shipped, f"«{nombre}» se cayó de la lista — es uno de los que rompieron en vivo"


def test_la_lista_no_gasta_huecos_en_los_que_deepgram_ya_acierta():
    """El defecto simétrico, y el que tendría una lista ordenada por población: quemar el presupuesto en
    Madrid y Barcelona, que nova-3 transcribe bien, y no llegar a los que fallan."""
    shipped = {t.lower() for t in gz._load("es")}
    for nombre in ("madrid", "barcelona", "sevilla", "bilbao"):
        assert nombre not in shipped, f"«{nombre}» no falla; ocupa un hueco que necesita otro"


# ── el cableado: mandar la lista, y NO mandarla cuando mandarla rompe ───────────────────────────────────────

def test_una_sesion_en_castellano_manda_los_terminos(monkeypatch):
    monkeypatch.setattr(langs, "first_run_auto", lambda: False)
    monkeypatch.setattr(langs, "current_code", lambda: "es")
    stt = dg.build()
    assert stt._opts.keyterm, "la sesión del operador no lleva refuerzo: el gazetteer no está cableado"
    assert "Calatayud" in stt._opts.keyterm


def test_la_primera_ejecucion_NO_manda_terminos(monkeypatch):
    """Con el idioma sin elegir el STT va en `multi` para que `i18n.init.detect` clasifique la primera frase.
    Sembrarla de topónimos españoles sesga justo esa decisión."""
    monkeypatch.setattr(langs, "first_run_auto", lambda: True)
    stt = dg.build()
    assert not stt._opts.keyterm


def test_un_modelo_que_no_es_nova3_NO_manda_terminos(monkeypatch):
    """Guarda de CABLEADO y el más caro de todos: el plugin LANZA con `keyterm` fuera de nova-3, y lo hace
    mientras se construye la sesión — o sea que un `ZAELAR_STT_MODEL_DG=nova-2` se llevaría por delante el STT
    entero. Aquí se comprueba que se construye, no que la condición esté escrita."""
    import dataclasses

    from voice.engine.core.config import SETTINGS
    monkeypatch.setattr(langs, "first_run_auto", lambda: False)
    monkeypatch.setattr(langs, "current_code", lambda: "es")
    # `SETTINGS` es un dataclass CONGELADO, así que no se le puede asignar el campo: se sustituye el objeto que
    # ve el módulo. Vale la pena dejarlo escrito porque la primera versión de este test falló por eso y no por
    # el código que mide.
    monkeypatch.setattr(dg, "SETTINGS", dataclasses.replace(SETTINGS, stt_model_deepgram="nova-2"))
    stt = dg.build()                       # si el guarda no está, esto es un ValueError y no un assert
    assert not stt._opts.keyterm


# ── el enganche a la memoria: PREPARADO Y APAGADO ───────────────────────────────────────────────────────────

def test_la_memoria_esta_apagada_por_defecto(monkeypatch):
    """Encenderlo manda a un tercero los nombres de la gente que conoce y los sitios donde ha estado. Es una
    decisión del operador con su coste dicho, no un defecto que se cuela."""
    monkeypatch.delenv(gz.MEMORY_ENV, raising=False)
    assert gz.memory_terms() == []


def test_encendido_saca_nombres_propios_de_su_memoria(monkeypatch):
    monkeypatch.setenv(gz.MEMORY_ENV, "1")
    import memory.api as _mem
    monkeypatch.setattr(_mem, "state", lambda: {"operator_name": "Ricart",
                                                "location": "Vive en Calatayud, Aragón",
                                                "familia": "su hermana Núria"})
    out = gz.memory_terms()
    assert "Calatayud" in out and "Núria" in out
    assert "vive" not in [t.lower() for t in out], "una palabra en minúscula no es un nombre propio"
