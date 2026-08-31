"""V2-452 · the prompt is in Spanish and the operator speaks English: the model was copying its language.

All the blocks in this prompt—the lock, the state, the background tasks, the browser-facing text—are in
Spanish, even when the configured language is another one. The lock already said «always and ONLY respond in
English» and it was not enough: **it did not name what must NOT be copied**, which is the lesson from V2-221
(without the phrase inside it, the model has nothing against which to compare itself).

Measured across the 40 saved US rounds (2026-08-28): **8 (20 %) contain Spanish in zaelar's voice**, and
in THREE it responds entirely in Spanish to an English speaker—«Me pongo con ello: busco un DSLR de segunda
mano…», «Hecho, te aviso en cuanto tenga candidatos», «Sigo sin novedades»—. The other five contain a single
isolated word within an English sentence («Bueno», «todavía»), which is the exact signature of copying.

And it is NOT that the language is set incorrectly: the mechanism for those rounds contains
`memory_language: {"effective": "en", "explicit": true}`. The engine knows the language; what was missing was
telling the model that what it READS is deliberately in another language.
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
    """The lesson from V2-221: naming the phrase being replaced is what allows comparison. All four come from
    the reports, not from imagination."""
    t = _lock(monkeypatch, "en")
    for w in ("Bueno", "todavía", "la hoja", "candidatos"):
        assert w in t


def test_los_saludos_y_despedidas_entran_en_la_regla(monkeypatch):
    """Three of the eight measured cases are exactly that: an English response ending in «Bueno…»."""
    assert "despedidas" in _lock(monkeypatch, "en")


def test_con_operador_en_CASTELLANO_el_lock_no_cambia(monkeypatch):
    """Sensitivity: the half of the board that is performing better must not pay for this fix. The notice would
    be superfluous—the notes are ALREADY in their language—and adding text to the prompt on every turn for a
    defect that does not exist there is the wrong trade-off."""
    t = _lock(monkeypatch, "es")
    assert "NOTAS INTERNAS" not in t and "NUNCA copies" not in t


def test_y_el_lock_de_siempre_sigue_entero(monkeypatch):
    """The notice is ADDED, not substituted: the absolute rule and the rule to assist in any language remain."""
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
