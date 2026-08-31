"""V2-490 — the critical limit is repeated AT THE END of the state, phrased as a check rather than a biography.

Measured over 4 rounds of `knows-who-i-am-without-being-told-again` (2026-08-29): **2 of 4 red**, and in both
the same finding — «Proposed macaroni to a celiac user». The data **did arrive** as a limit: two
`critical='health'` pills, importance 0.95, pinned, and the «⚠️ CRÍTICO» line present in the
state block. This is not plumbing: it is OBEDIENCE, the same class that was already closed out five times tonight on the
delivery side.

What is fixed here is the PROPERTY for which the change was made: that the limit be the last thing read and that it
be stated as a check on what is going to be said. **The wording** is not fixed.

⚠️ Whether this FIXES the behavior has not been measured — the bar is 6 rounds. A guard cannot assert what has not
been measured, so none of these cases says that the model obeys; they say where and how the phrase arrives.
"""
import pytest

from memory import _prompt


@pytest.fixture
def _sin_base(monkeypatch):
    """The composer reads the real database. Here the data is supplied manually: a unit test does not touch live artifacts."""
    monkeypatch.setattr(_prompt, "salient_long", lambda **k: [])
    monkeypatch.setattr(_prompt, "recent_short", lambda **k: [])


def _componer(monkeypatch, crit, **estado):
    monkeypatch.setattr(_prompt, "critical_facts", lambda limit=6: crit)
    st = {"operator_name": "Marc"}
    st.update(estado)
    monkeypatch.setattr(_prompt._state, "read", lambda: st)
    return _prompt.compose_state(mission_fallback="")


def test_el_limite_es_LO_ULTIMO_que_se_lee(_sin_base, monkeypatch):
    """At the top it is fifth among a dozen entries; here it is the last thing before the turn."""
    block, _op, _st = _componer(monkeypatch, ["es celíaco, nada con gluten"],
                                location="Madrid", open_widgets=["agenda", "navegador"])
    assert "LÍMITES QUE NO PUEDES SALTARTE" in block
    assert block.rstrip().endswith("cuenta como habérselo propuesto."), (
        "el límite ha dejado de ser lo último que se lee")


def test_esta_dicho_como_COMPROBACION_no_como_biografia(_sin_base, monkeypatch):
    """«Es celíaco» is a fact about the person, and the model reads it as biography. The final phrase has
    to talk about what it is going to SAY."""
    block, _, _ = _componer(monkeypatch, ["es celíaco, nada con gluten"])
    cola = block.split("LÍMITES QUE NO PUEDES SALTARTE")[1]
    assert "Antes de PROPONERLE" in cola and "compruéba" in cola


def test_nombra_el_fallo_MEDIDO_de_proponer_y_matizar(_sin_base, monkeypatch):
    """The red round said «pasta or rice» and clarified afterward that the pasta was gluten-free. Without the phrase inside, the
    model has nothing against which to check itself — the lesson of V2-221."""
    block, _, _ = _componer(monkeypatch, ["es celíaco, nada con gluten"])
    assert "matizarlo después cuenta como habérselo propuesto" in block


def test_SIN_hechos_criticos_el_prompt_sale_IGUAL_que_antes(_sin_base, monkeypatch):
    """Zero cost for anyone with no restrictions: not one extra line."""
    block, _, _ = _componer(monkeypatch, [], location="Madrid")
    assert "LÍMITES" not in block and "⚠️" not in block


def test_el_hecho_sigue_TAMBIEN_en_su_sitio_de_siempre(_sin_base, monkeypatch):
    """The repetition is deliberate: above it situates the person; below it governs the response. Removing the one
    above would leave the «who you have in front of you» block without a fact that belongs to it."""
    block, _, _ = _componer(monkeypatch, ["es celíaco, nada con gluten"])
    assert "CRÍTICO (tenlo SIEMPRE presente)" in block
    assert block.count("es celíaco, nada con gluten") == 2


def test_no_hay_NINGUNA_palabra_de_dominio_en_el_codigo():
    """What governs is the CLASS of the fact (`meta.critical`), not its content. A list of foods here
    would be adapting to the use case, which is precisely what is forbidden — the agent handles ANY task."""
    fuente = open(_prompt.__file__, encoding="utf-8").read()
    bloque = fuente.split("LÍMITES QUE NO PUEDES SALTARTE")[1][:600]
    for palabra in ("gluten", "celíac", "celiac", "alcohol", "pasta", "lactosa", "fruto seco"):
        assert palabra not in bloque.lower(), f"«{palabra}» convierte el guarda en un filtro de dominio"
