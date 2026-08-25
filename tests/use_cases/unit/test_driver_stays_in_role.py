"""The tester leaving its own role, and not knowing what year it is, both make a round measure nothing.

Both measured on 2026-08-20 in `weekend-adventure-sports-bilbao__es`, which scored 1/5 and should have scored
nothing at all:

· The persona asked for "this weekend, Saturday 22 and Sunday 23 August". zaelar resolved 22-23 August 2026 —
  correct — and the driver rejected it twice ("nada de 2026… es de este año, el próximo"), burning three turns,
  after which the judge filed zaelar for date confusion. The judge got its calendar that same morning for the
  mirror-image bug; giving it to one side only moves which participant is confidently wrong.
· Later the "tester" turn delivered the assistant's answer — surf schools and canyoning with prices and URLs —
  and zaelar replied, sensibly, that the message looked cut off. Grading that grades the harness.
"""
from __future__ import annotations

import datetime

import pytest

from tests.use_cases.e2e.agent import driver as D, judge as J


def _scn():
    from tests.use_cases.e2e.agent import scenarios as SC
    return SC.UseCaseScenario(id="x", locale="es", tier=1, persona_brief="quieres un plan",
                              opening_line="o", success_checks="s")


_DELIVERY = """Te paso lo que he encontrado:
**Surf** (nivel principiante-medio)
- Escuela: **Bilbao Surf School** (Sopelana). Clase de 2h: 35-40€/persona.
  https://bilbaosurfschool.com
- Escuela: **Peña Txuri Surf Eskola**. Alquiler 20€/persona, clase 35€.
  https://penatxurisurfeskola.com"""


def test_the_driver_is_told_what_year_it_is():
    hoy = datetime.date.today()
    sys = D.Driver(_scn()).history[0]["content"]
    assert hoy.isoformat() in sys
    assert f"El año en curso es {hoy.year}" in sys
    assert "NO la corrijas" in sys, "sin esta frase el driver corrige una fecha correcta y la ronda se pierde"


def test_a_deliverable_is_recognised_as_leaving_the_role():
    assert D.looks_like_the_assistant(_DELIVERY) is True


def test_a_real_person_writing_a_long_message_is_NOT():
    """Sensitivity, and it matters: personas do write long, and they do paste links. If this misfired the
    harness would retry good turns and eventually call healthy rounds INFRA."""
    for ok in ("Vale, mira a ver y me dices, que no tengo prisa.",
               "Perdona, te dije en Madrid, y son dos entradas. De precio no quiero pasarme, algo de zona "
               "media está bien, y si puede ser función de tarde mejor que de noche, que luego se hace "
               "tardísimo para volver y mañana trabajo temprano.",
               "Mira en https://entradas.com a ver si hay algo, que un amigo me dijo que ahí salían más "
               "baratas y yo no me aclaro con esas webs, siempre acabo pagando gastos de gestión."):
        assert D.looks_like_the_assistant(ok) is False, ok[:60]


def test_it_RETRIES_once_and_keeps_the_recovered_line(monkeypatch):
    said = iter([_DELIVERY, "Ah vale, pues dime cuál te parece mejor de las dos."])
    monkeypatch.setattr(D.llm, "call", lambda *a, **k: next(said))
    d = D.Driver(_scn())
    txt = d.reply()
    assert txt.startswith("Ah vale")
    assert d.role_flips == 1, "un flip recuperado se cuenta, para que la ronda lo diga"


def test_a_flip_that_SURVIVES_is_counted_twice(monkeypatch):
    monkeypatch.setattr(D.llm, "call", lambda *a, **k: _DELIVERY)
    d = D.Driver(_scn())
    d.reply()
    assert d.role_flips == 2, "si no vuelve al papel hay que poder distinguirlo de un flip recuperado"


def test_the_judge_is_told_the_absurd_turn_was_OURS():
    txt = J.mechanism_facts({"role_flips": 2})
    assert "AVERÍA DEL ARNÉS" in txt
    assert "ESO ES NUESTRO" in txt
    assert "No puntúes a zaelar" in txt


def test_and_says_nothing_when_the_driver_behaved():
    assert "AVERÍA DEL ARNÉS" not in J.mechanism_facts({"families_observed": ["flash"]})


# ── V2-312: dos caras más del flip, medidas en la MISMA ronda (find-direct-flight-budget__es, 10:42) ─────────
#
# El juez puntuó adaptación 1/5 sobre un diálogo donde el TESTER hablaba como agente en dos turnos seguidos, y
# `role_flips` salió vacío: ninguna de las seis caras las vio. Sin esa marca la ronda se puntúa como si el
# producto hubiera hecho lo que hizo el arnés — la familia del instrumento acusando al producto.

def test_rehacer_el_trabajo_tambien_es_prometer_entrega():
    """«Lo rehago ya… te aviso en cuanto lo tenga»: la mitad de la ENTREGA sí casaba; la del TRABAJO no,
    porque solo conocía «sigo en ello»."""
    linea = ("Ay, perdona, tienes toda la razón, me hice un lío con las fechas. Lo rehago ya para el finde "
             "del 15 de septiembre, con equipaje de mano incluido. Te aviso en cuanto lo tenga.")
    assert D.looks_like_the_assistant(linea, "Marc") is True


def test_narrar_NUESTRA_maquinaria_en_primera_persona_es_un_flip():
    """Una persona no sortea la verificación anti-robot del navegador del agente ni filtra sus resultados.
    Lo que delata no es el VERBO (uno filtra su propio correo) sino el OBJETO."""
    linea = ("Te cuento: la búsqueda va un poco lenta por la verificación que pedía Skyscanner, pero ya la he "
             "sorteado y estoy filtrando solo salidas alrededor del 15 de septiembre.")
    assert D.looks_like_the_assistant(linea, "Marc") is True


@pytest.mark.parametrize("linea", [
    "vale, yo también miro por mi cuenta en Wallapop mientras tanto",
    "la búsqueda va lenta, ¿no? ¿sigue viva?",
    "he mirado mi calendario y me va bien el 15",
    "estoy mirando mi correo, dame un segundo",
    "¿has sorteado ya la verificación esa?",
    "ok, avísame cuando lo tengas",
])
def test_y_la_persona_SIGUE_pudiendo_hablar_normal(linea):
    """La mitad cara del detector: un falso positivo marca la ronda como avería del arnés y tira una medida
    buena. Estas seis son cosas que una persona real dice — cuatro de ellas nombran nuestra maquinaria."""
    assert D.looks_like_the_assistant(linea, "Marc") is False
