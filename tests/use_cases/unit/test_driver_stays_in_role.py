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


# ── V2-312: two more faces of the flip, measured in the SAME round (find-direct-flight-budget__es, 10:42) ───
#
# The judge scored adaptation 1/5 on a dialogue where the TESTER spoke like an agent for two consecutive turns, and
# `role_flips` came out empty: none of the six faces saw them. Without that marker, the round is scored as though the
# product had done what the harness did—the instrument's family accusing the product.

def test_rehacer_el_trabajo_tambien_es_prometer_entrega():
    """“I’ll redo it now…I’ll let you know as soon as I have it”: the DELIVERY half did match; the WORK half did not,
    because it only knew “I’m still working on it”."""
    linea = ("Ay, perdona, tienes toda la razón, me hice un lío con las fechas. Lo rehago ya para el finde "
             "del 15 de septiembre, con equipaje de mano incluido. Te aviso en cuanto lo tenga.")
    assert D.looks_like_the_assistant(linea, "Marc") is True


def test_narrar_NUESTRA_maquinaria_en_primera_persona_es_un_flip():
    """A person does not bypass the agent browser’s anti-robot verification or filter its results.
    What gives it away is not the VERB (one can filter one’s own email) but the OBJECT."""
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
    """The detector’s face half: a false positive marks the round as a harness failure and discards a
    good measurement. These six are things a real person says—four of them mention our machinery."""
    assert D.looks_like_the_assistant(linea, "Marc") is False
