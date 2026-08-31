"""voice/engine/speech/stt/gazetteer.py — reinforcement of terms for the remote STT.

The incident that motivated it is real and measured: Deepgram split «Calatayud» into «cal»+«a», the segmenter joined 23
fragments, and the distiller ended up writing that the operator lives somewhere he does not. These tests cover
the two halves that matter: that the names that failed ARE present, and that the list cannot grow until it leaves
the engine deaf — exceeding Deepgram’s limit produces a 400 on the listening request, meaning no STT.
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


# ── the measured envelope: exceeding it means going DEAF ─────────────────────────────────────────────────────

def test_la_lista_que_se_publica_cabe_en_el_tope_de_deepgram():
    """The real ratchet. Deepgram counts SUB-TOKENS, not entries, so there is no way to count them from here:
what is stored is the envelope measured against the live API (114 real names / 1221 chars on 2026-08-23) with
headroom, because these names are rarer than the ones that were bisected and cost more tokens each. If someone
adds twenty towns, this test turns red BEFORE the operator loses their voice."""
    shipped = gz._load("es")
    assert shipped, "without a list there is no reinforcement — the data file is not being published"
    assert len(shipped) <= gz.MAX_TERMS, f"{len(shipped)} terms exceed the measured limit ({gz.MAX_TERMS})"
    assert sum(len(t) for t in shipped) <= gz.MAX_CHARS


def test_el_clamp_recorta_aunque_el_fichero_crezca():
    """Belt as well as braces: the test above guards the file; this one guards the call. One too many is not a
town transcribed incorrectly; it is the entire session left untranscribed."""
    assert len(gz._clamp([f"Pueblo{i}" for i in range(500)])) <= gz.MAX_TERMS
    assert sum(len(t) for t in gz._clamp(["x" * 100] * 50)) <= gz.MAX_CHARS


def test_un_idioma_sin_lista_no_refuerza_nada():
    assert gz.terms("ja") == []
    assert gz.terms("") == []


# ── make the fix REACH the incident that motivated it ─────────────────────────────────────────────────────────

def test_los_nombres_que_fallaron_estan_en_la_lista():
    """Without this, the module can be perfect and still be useless. These two are from the operator’s incident,
and they are exactly the ones a POPULATION-based criterion would have left out: Calatayud is #429 and Valls
is #321, so neither would fit among 114 slots. That is why the criterion is measured risk, not size."""
    shipped = {t.lower() for t in gz._load("es")}
    for nombre in ("calatayud", "valls"):
        assert nombre in shipped, f"«{nombre}» se cayó de la lista — es uno de los que rompieron en vivo"


def test_la_lista_no_gasta_huecos_en_los_que_deepgram_ya_acierta():
    """The symmetrical defect, and the one a population-ordered list would have: burning the budget on Madrid
and Barcelona, which nova-3 transcribes correctly, and never reaching the ones that fail."""
    shipped = {t.lower() for t in gz._load("es")}
    for nombre in ("madrid", "barcelona", "sevilla", "bilbao"):
        assert nombre not in shipped, f"«{nombre}» no falla; ocupa un hueco que necesita otro"


# ── the wiring: send the list, and DO NOT send it when doing so breaks things ───────────────────────────────

def test_una_sesion_en_castellano_manda_los_terminos(monkeypatch):
    monkeypatch.setattr(langs, "first_run_auto", lambda: False)
    monkeypatch.setattr(langs, "current_code", lambda: "es")
    stt = dg.build()
    assert stt._opts.keyterm, "the operator’s session has no reinforcement: the gazetteer is not wired in"
    assert "Calatayud" in stt._opts.keyterm


def test_la_primera_ejecucion_NO_manda_terminos(monkeypatch):
    """When no language has been selected, the STT runs in `multi` so that `i18n.init.detect` can classify the
first sentence. Seeding it with Spanish place names biases exactly that decision."""
    monkeypatch.setattr(langs, "first_run_auto", lambda: True)
    stt = dg.build()
    assert not stt._opts.keyterm


def test_un_modelo_que_no_es_nova3_NO_manda_terminos(monkeypatch):
    """Wiring safeguard and the most costly one: the plugin CRASHES with `keyterm` outside nova-3, and it does so
while the session is being built — meaning a `ZAELAR_STT_MODEL_DG=nova-2` would bring down the entire STT.
This checks that it builds, not that the condition is written."""
    import dataclasses

    from voice.engine.core.config import SETTINGS
    monkeypatch.setattr(langs, "first_run_auto", lambda: False)
    monkeypatch.setattr(langs, "current_code", lambda: "es")
    # `SETTINGS` is a FROZEN dataclass, so its field cannot be assigned: the object seen by the module is replaced.
    # It is worth documenting this because the first version of this test failed for that reason, not because of
    # the code under test.
    monkeypatch.setattr(dg, "SETTINGS", dataclasses.replace(SETTINGS, stt_model_deepgram="nova-2"))
    stt = dg.build()                       # without the safeguard, this is a ValueError, not an assertion failure
    assert not stt._opts.keyterm


# ── the memory hook: READY AND OFF ──────────────────────────────────────────────────────────────────────────

def test_la_memoria_esta_apagada_por_defecto(monkeypatch):
    """Turning it on sends a third party the names of people it knows and the places it has been. It is an
operator decision with its cost stated, not a defect that slips in unnoticed."""
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
