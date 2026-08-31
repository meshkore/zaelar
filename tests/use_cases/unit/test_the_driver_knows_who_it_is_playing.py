"""The driver and watchdog must know what the AGENT already knows about the person (2026-08-24).

Measured in round 12 of `search-buy-guitar__es`. The set seeds a profile—Marc, lives in Madrid—and the
header of `tests/use_cases/lab/profiles.py` says what it exists for, in these words: “the layer that makes
“find me a plumber” resolve to the correct country WITHOUT ANYONE SAYING A CITY.” The agent did
exactly that: it resolved “nearby so I can test it” to Madrid.

And the harness punished it twice over, because neither the driver nor the watchdog knew the profile existed:

  · the DRIVER applied its general correction instruction (“sorry, I didn’t say it was in Madrid”—
    literally true, because it knew this from MEMORY, and therefore irrelevant);
  · the WATCHDOG marked `off_track` TWICE, because the canonical example in its own prompt was, word
    for word, “a city the user did not mention.”

Five of the ten turns were spent on a fabricated argument. And the costly part came afterward: the agent
apologized and WROTE the correction—`operator.location` ended up saying “Marc has not confirmed that he
lives in Madrid.” Memory is shared among the cases in a batch, so one case destroyed the seeded profile
for all those that followed.

What these cases establish is the boundary: REMEMBERING IS NOT INVENTING. A profile datum provided as known
is correct behavior; a datum the agent cannot know from anywhere remains a failure—and there is a case for
each side, because “never correct” would break half of the harness that measures adaptation.
"""
from tests.use_cases.e2e.agent import config, driver as drivermod, watchdog
from tests.use_cases.lab import profiles as labp


class _Scn:
    id = "x__es"
    locale = "es"
    opening_line = "Encuéntrame una guitarra acústica de segunda mano por menos de 150€."
    persona_brief = "Quieres una guitarra barata."
    success_checks = "Tres guitarras con precio y enlace."


def _driver_system(scn=_Scn()):
    return drivermod.Driver(scn).history[0]["content"]


# ---------------------------------------------------------------------------- the profile is DERIVED from the set

def test_el_perfil_se_deriva_del_MISMO_sitio_que_siembra_la_base():
    """Two copies of a fact diverge, and here diverging means that the driver starts arguing again."""
    g = labp.ES.persona_ground()
    assert labp.ES.state["operator_name"] in g
    assert labp.ES.state["location"] in g
    g_us = labp.US.persona_ground()
    assert labp.US.state["operator_name"] in g_us and labp.US.state["location"] in g_us


def test_cada_agente_habla_en_SU_idioma():
    """A Spanish-language block in the US agent's prompt teaches it to respond in the wrong language."""
    assert "Quién eres" in labp.ES.persona_ground()
    assert "Who you are" in labp.US.persona_ground()


def test_un_perfil_SIN_datos_no_dice_nada():
    """Outside the set there is no profile, so the driver must remain exactly as it was."""
    vacio = labp.LabProfile(key="x", port=1, language="es", title="t")
    assert vacio.persona_ground() == ""


# ---------------------------------------------------------------------------- the DRIVER

def test_el_conductor_recibe_quien_es(monkeypatch):
    monkeypatch.setattr(config, "PERSONA_PROFILE", labp.ES.persona_ground())
    sysmsg = _driver_system()
    assert "Marc" in sysmsg and "Madrid" in sysmsg
    assert "no le digas «yo no he dicho eso»" in sysmsg, (
        "la prohibición TIENE que estar literal: es la frase exacta que el conductor produjo")


def test_va_DELANTE_del_encargo(monkeypatch):
    """The driver reads from top to bottom, and the instruction to “correct what it misunderstands” comes below. Behind it,
    this block arrives too late: the order is what makes it a framework rather than a footnote."""
    monkeypatch.setattr(config, "PERSONA_PROFILE", labp.ES.persona_ground())
    sysmsg = _driver_system()
    assert sysmsg.index("Quién eres") < sysmsg.index("Lo que quieres conseguir")


def test_sin_plato_el_prompt_del_conductor_es_EL_DE_SIEMPRE(monkeypatch):
    """Sensitivity in the other direction: if this changed the prompt outside the set, it would change what is measured by
    every run that does not use a seeded agent, and nobody asked for that change."""
    monkeypatch.setattr(config, "PERSONA_PROFILE", "")
    sysmsg = _driver_system()
    assert "Quién eres" not in sysmsg
    assert "\n\n## Lo que quieres conseguir" in sysmsg, "sin perfil no puede quedar un hueco raro en medio"


def test_el_agente_US_recibe_su_bloque_en_ingles(monkeypatch):
    class _US(_Scn):
        locale = "us"
    monkeypatch.setattr(config, "PERSONA_PROFILE", labp.US.persona_ground())
    sysmsg = drivermod.Driver(_US()).history[0]["content"]
    assert "Who you are" in sysmsg and "San Francisco" in sysmsg
    assert sysmsg.index("Who you are") < sysmsg.index("What you want")


# ---------------------------------------------------------------------------- the WATCHDOG

def test_el_vigilante_recibe_quien_es(monkeypatch):
    monkeypatch.setattr(config, "PERSONA_PROFILE", labp.ES.persona_ground())
    msgs = watchdog.build_messages(_Scn(), [{"who": "tester", "text": "hola"}])
    user = msgs[-1]["content"]
    assert "LO QUE ZAELAR YA SABE DE ESTA PERSONA" in user and "Madrid" in user


def test_el_vigilante_ya_NO_pone_de_ejemplo_la_ciudad_que_el_usuario_no_dijo():
    """It was the canonical example in its prompt, word for word, and it triggered on the profile's function."""
    assert "una ciudad que el usuario no dijo" not in watchdog._SYSTEM
    assert "RECORDAR NO ES INVENTAR" in watchdog._SYSTEM


def test_el_vigilante_SIGUE_pudiendo_marcar_lo_que_el_agente_no_puede_saber():
    """“Never correct” would break half of the harness that measures adaptation: the boundary is what is KNOWABLE."""
    sysmsg = watchdog._SYSTEM
    assert "sí es off_track" in sysmsg
    assert "ignoró una respuesta" in sysmsg, "corregir un dato ya dado en la conversación sigue siendo su trabajo"


def test_sin_plato_el_vigilante_no_ve_bloque_de_perfil(monkeypatch):
    monkeypatch.setattr(config, "PERSONA_PROFILE", "")
    user = watchdog.build_messages(_Scn(), [{"who": "tester", "text": "hola"}])[-1]["content"]
    assert "LO QUE ZAELAR YA SABE" not in user
