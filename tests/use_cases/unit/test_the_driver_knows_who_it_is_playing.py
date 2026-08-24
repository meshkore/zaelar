"""El conductor y el vigilante tienen que saber lo que el AGENTE ya sabe de la persona (2026-08-24).

Medido en la ronda 12 de `search-buy-guitar__es`. El plató siembra un perfil —Marc, vive en Madrid— y la
cabecera de `tests/use_cases/lab/profiles.py` dice para qué existe, con estas palabras: «la capa que hace
que "búscame un fontanero" resuelva al país correcto SIN QUE NADIE DIGA UNA CIUDAD». El agente hizo
exactamente eso: resolvió «cerca para poder probarla» a Madrid.

Y el arnés lo castigó por partida doble, porque ni el conductor ni el vigilante sabían que existía el perfil:

  · el CONDUCTOR aplicó su instrucción general de corregir («perdona, yo no he dicho que sea en Madrid» —
    literalmente cierto, porque lo sabía por MEMORIA, y por eso irrelevante);
  · el VIGILANTE marcó `off_track` DOS veces, porque el ejemplo canónico de su propio prompt era, palabra
    por palabra, «una ciudad que el usuario no dijo».

Cinco de los diez turnos se fueron en una discusión fabricada. Y lo caro vino después: el agente se
disculpó y ESCRIBIÓ la corrección — `operator.location` acabó diciendo «Marc no ha confirmado que viva en
Madrid». La memoria se comparte entre los casos de una tanda, así que un caso destruyó el perfil sembrado
para todos los que venían detrás.

Lo que estos casos fijan es la frontera: RECORDAR NO ES INVENTAR. Un dato del perfil dado por sabido es
conducta correcta; un dato que el agente no puede saber por ningún lado sigue siendo un fallo — y hay un
caso para cada lado, porque «no corrijas nunca» rompería la mitad del arnés que mide adaptación.
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


# ---------------------------------------------------------------------------- el perfil se DERIVA del plató

def test_el_perfil_se_deriva_del_MISMO_sitio_que_siembra_la_base():
    """Dos copias de un hecho se separan, y aquí separarse significa que el conductor vuelva a discutir."""
    g = labp.ES.persona_ground()
    assert labp.ES.state["operator_name"] in g
    assert labp.ES.state["location"] in g
    g_us = labp.US.persona_ground()
    assert labp.US.state["operator_name"] in g_us and labp.US.state["location"] in g_us


def test_cada_agente_habla_en_SU_idioma():
    """Un bloque en castellano dentro del prompt del agente US le enseña a contestar en el idioma que no es."""
    assert "Quién eres" in labp.ES.persona_ground()
    assert "Who you are" in labp.US.persona_ground()


def test_un_perfil_SIN_datos_no_dice_nada():
    """Fuera del plató no hay perfil, y entonces el conductor tiene que quedarse exactamente como estaba."""
    vacio = labp.LabProfile(key="x", port=1, language="es", title="t")
    assert vacio.persona_ground() == ""


# ---------------------------------------------------------------------------- el CONDUCTOR

def test_el_conductor_recibe_quien_es(monkeypatch):
    monkeypatch.setattr(config, "PERSONA_PROFILE", labp.ES.persona_ground())
    sysmsg = _driver_system()
    assert "Marc" in sysmsg and "Madrid" in sysmsg
    assert "no le digas «yo no he dicho eso»" in sysmsg, (
        "la prohibición TIENE que estar literal: es la frase exacta que el conductor produjo")


def test_va_DELANTE_del_encargo(monkeypatch):
    """El conductor lee de arriba abajo y la instrucción de «corrige lo que entienda mal» va abajo. Detrás,
    este bloque llega tarde: es el orden lo que lo hace un marco y no una nota al pie."""
    monkeypatch.setattr(config, "PERSONA_PROFILE", labp.ES.persona_ground())
    sysmsg = _driver_system()
    assert sysmsg.index("Quién eres") < sysmsg.index("Lo que quieres conseguir")


def test_sin_plato_el_prompt_del_conductor_es_EL_DE_SIEMPRE(monkeypatch):
    """Sensibilidad por el otro lado: si esto cambiara el prompt fuera del plató, cambiaría lo que miden
    todas las corridas que no usan un agente sembrado, y ese cambio no lo pidió nadie."""
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


# ---------------------------------------------------------------------------- el VIGILANTE

def test_el_vigilante_recibe_quien_es(monkeypatch):
    monkeypatch.setattr(config, "PERSONA_PROFILE", labp.ES.persona_ground())
    msgs = watchdog.build_messages(_Scn(), [{"who": "tester", "text": "hola"}])
    user = msgs[-1]["content"]
    assert "LO QUE ZAELAR YA SABE DE ESTA PERSONA" in user and "Madrid" in user


def test_el_vigilante_ya_NO_pone_de_ejemplo_la_ciudad_que_el_usuario_no_dijo():
    """Era el ejemplo canónico de su prompt, palabra por palabra, y disparaba sobre la función del perfil."""
    assert "una ciudad que el usuario no dijo" not in watchdog._SYSTEM
    assert "RECORDAR NO ES INVENTAR" in watchdog._SYSTEM


def test_el_vigilante_SIGUE_pudiendo_marcar_lo_que_el_agente_no_puede_saber():
    """«No corrijas nunca» rompería la mitad del arnés que mide adaptación: la frontera es lo SABIBLE."""
    sysmsg = watchdog._SYSTEM
    assert "sí es off_track" in sysmsg
    assert "ignoró una respuesta" in sysmsg, "corregir un dato ya dado en la conversación sigue siendo su trabajo"


def test_sin_plato_el_vigilante_no_ve_bloque_de_perfil(monkeypatch):
    monkeypatch.setattr(config, "PERSONA_PROFILE", "")
    user = watchdog.build_messages(_Scn(), [{"who": "tester", "text": "hola"}])[-1]["content"]
    assert "LO QUE ZAELAR YA SABE" not in user
