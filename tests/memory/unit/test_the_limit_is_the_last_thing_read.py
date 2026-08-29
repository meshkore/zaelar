"""V2-490 — el límite crítico se repite AL FINAL del estado, dicho como comprobación y no como biografía.

Medido sobre 4 rondas de `knows-who-i-am-without-being-told-again` (2026-08-29): **2 de 4 rojas**, y en las
dos el mismo hallazgo — «Propuso macarrones a un usuario celíaco». El dato **sí llegaba** como límite: dos
píldoras `critical='health'`, importancia 0,95, pineadas, y la línea «⚠️ CRÍTICO» presente en el bloque de
estado. No es fontanería: es OBEDIENCIA, la misma clase que esta noche ya se cerró cinco veces por el lado de
la entrega.

Lo que se fija aquí es la PROPIEDAD por la que se hizo el cambio: que el límite sea lo último que se lee y que
esté enunciado como comprobación sobre lo que se va a decir. **No** se fija la redacción.

⚠️ Que esto ARREGLE la conducta está sin medir — el listón son 6 rondas. Un guarda no puede afirmar lo que no
se ha medido, así que ninguno de estos casos dice que el modelo obedezca; dicen dónde y cómo llega la frase.
"""
import pytest

from memory import _prompt


@pytest.fixture
def _sin_base(monkeypatch):
    """El compositor lee la base real. Aquí se le dan los datos a mano: un unitario no toca artefactos vivos."""
    monkeypatch.setattr(_prompt, "salient_long", lambda **k: [])
    monkeypatch.setattr(_prompt, "recent_short", lambda **k: [])


def _componer(monkeypatch, crit, **estado):
    monkeypatch.setattr(_prompt, "critical_facts", lambda limit=6: crit)
    st = {"operator_name": "Marc"}
    st.update(estado)
    monkeypatch.setattr(_prompt._state, "read", lambda: st)
    return _prompt.compose_state(mission_fallback="")


def test_el_limite_es_LO_ULTIMO_que_se_lee(_sin_base, monkeypatch):
    """Arriba queda quinto de una docena de entradas; aquí es lo último antes del turno."""
    block, _op, _st = _componer(monkeypatch, ["es celíaco, nada con gluten"],
                                location="Madrid", open_widgets=["agenda", "navegador"])
    assert "LÍMITES QUE NO PUEDES SALTARTE" in block
    assert block.rstrip().endswith("cuenta como habérselo propuesto."), (
        "el límite ha dejado de ser lo último que se lee")


def test_esta_dicho_como_COMPROBACION_no_como_biografia(_sin_base, monkeypatch):
    """«Es celíaco» es un hecho sobre la persona y el modelo lo lee como biografía. La frase del final tiene
    que hablar de lo que va a DECIR."""
    block, _, _ = _componer(monkeypatch, ["es celíaco, nada con gluten"])
    cola = block.split("LÍMITES QUE NO PUEDES SALTARTE")[1]
    assert "Antes de PROPONERLE" in cola and "compruéba" in cola


def test_nombra_el_fallo_MEDIDO_de_proponer_y_matizar(_sin_base, monkeypatch):
    """La ronda roja dijo «pasta o arroz» y aclaró después que la pasta era sin gluten. Sin la frase dentro, el
    modelo no tiene con qué contrastarse — la lección de V2-221."""
    block, _, _ = _componer(monkeypatch, ["es celíaco, nada con gluten"])
    assert "matizarlo después cuenta como habérselo propuesto" in block


def test_SIN_hechos_criticos_el_prompt_sale_IGUAL_que_antes(_sin_base, monkeypatch):
    """Coste cero para quien no tiene ninguna restricción: ni una línea de más."""
    block, _, _ = _componer(monkeypatch, [], location="Madrid")
    assert "LÍMITES" not in block and "⚠️" not in block


def test_el_hecho_sigue_TAMBIEN_en_su_sitio_de_siempre(_sin_base, monkeypatch):
    """La repetición es deliberada: arriba sitúa a la persona, abajo gobierna la respuesta. Quitar la de
    arriba dejaría al bloque «quién tienes delante» sin un dato que le pertenece."""
    block, _, _ = _componer(monkeypatch, ["es celíaco, nada con gluten"])
    assert "CRÍTICO (tenlo SIEMPRE presente)" in block
    assert block.count("es celíaco, nada con gluten") == 2


def test_no_hay_NINGUNA_palabra_de_dominio_en_el_codigo():
    """Lo que gobierna es la CLASE del hecho (`meta.critical`), no su contenido. Una lista de alimentos aquí
    sería adaptarse al caso de uso, que es justo lo prohibido — el agente resuelve CUALQUIER encargo."""
    fuente = open(_prompt.__file__, encoding="utf-8").read()
    bloque = fuente.split("LÍMITES QUE NO PUEDES SALTARTE")[1][:600]
    for palabra in ("gluten", "celíac", "celiac", "alcohol", "pasta", "lactosa", "fruto seco"):
        assert palabra not in bloque.lower(), f"«{palabra}» convierte el guarda en un filtro de dominio"
