"""V2-452 · el prompt está en castellano y el operador habla inglés: el modelo copiaba su idioma.

Todos los bloques de este prompt —el lock, el estado, las tareas de fondo, la cara del navegador— están en
castellano, también cuando el idioma configurado es otro. El lock ya decía «responde SIEMPRE y ÚNICAMENTE en
English» y no bastaba: **no nombraba lo que NO hay que copiar**, que es la lección de V2-221 (sin la frase
dentro, el modelo no tiene con qué contrastarse).

Medido sobre las 40 rondas US guardadas (2026-08-28): **8 (20 %) llevan castellano en la voz de zaelar**, y
en TRES contesta entero en castellano a un angloparlante —«Me pongo con ello: busco un DSLR de segunda
mano…», «Hecho, te aviso en cuanto tenga candidatos», «Sigo sin novedades»—. Las otras cinco son una palabra
suelta dentro de una frase inglesa («Bueno», «todavía»), que es la firma exacta de la copia.

Y NO es que el idioma esté mal fijado: el mecanismo de esas rondas trae `memory_language: {"effective":
"en", "explicit": true}`. El motor sabe el idioma; lo que faltaba era decirle al modelo que lo que LEE está
en otra lengua a propósito.
"""
import importlib

import pytest


def _lock(monkeypatch, code):
    monkeypatch.setenv("ZAELAR_LANGUAGE", code)
    from nucleo.flash import prompt as P
    importlib.reload(P)
    return P._lang_lock()


def test_con_operador_en_INGLES_se_dice_que_las_notas_no_se_copian(monkeypatch):
    t = _lock(monkeypatch, "en")
    assert "NOTAS INTERNAS" in t and "NUNCA copies su lengua" in t
    assert "ENTERA en English" in t


def test_se_NOMBRAN_las_palabras_que_se_colaban(monkeypatch):
    """La lección de V2-221: nombrar la frase que se sustituye es lo que permite contrastarse. Las cuatro
    salen de los informes, no de la imaginación."""
    t = _lock(monkeypatch, "en")
    for w in ("Bueno", "todavía", "la hoja", "candidatos"):
        assert w in t


def test_los_saludos_y_despedidas_entran_en_la_regla(monkeypatch):
    """Tres de los ocho casos medidos son exactamente eso: una respuesta inglesa que acaba en «Bueno…»."""
    assert "despedidas" in _lock(monkeypatch, "en")


def test_con_operador_en_CASTELLANO_el_lock_no_cambia(monkeypatch):
    """Sensibilidad: la mitad del tablero que va mejor no puede pagar este arreglo. El aviso sobraría —las
    notas YA están en su idioma— y añadir texto al prompt de todos los turnos por un defecto que allí no
    existe es el canje equivocado."""
    t = _lock(monkeypatch, "es")
    assert "NOTAS INTERNAS" not in t and "NUNCA copies" not in t


def test_y_el_lock_de_siempre_sigue_entero(monkeypatch):
    """El aviso se AÑADE, no sustituye: la regla absoluta y la de atender en cualquier idioma siguen."""
    for code in ("en", "es"):
        t = _lock(monkeypatch, code)
        assert "REGLA ABSOLUTA" in t and "COMPRENDES cualquier idioma" in t


@pytest.fixture(autouse=True)
def _restaura():
    yield
    import os
    from nucleo.flash import prompt as P
    os.environ.pop("ZAELAR_LANGUAGE", None)
    importlib.reload(P)
