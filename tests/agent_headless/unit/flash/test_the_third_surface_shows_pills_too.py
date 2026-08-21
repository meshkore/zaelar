"""La TERCERA superficie que enseña píldoras a un modelo, y corría cada turno (V2-254).

Historia completa, porque la lección no está en el arreglo sino en cómo se encontró:

  · El arnés mandó un dato suelto: el agente buscó **«fontanero Soria»** teniendo `operator.location` = «Vive en
    el centro de Madrid». La píldora la escribía cada hora `widgets/meteo-soria`.
  · V2-242 cerró la ESCRITURA (una píldora de fondo lleva el nombre de quien la escribe en la clave).
  · memoria-dev cerró la LECTURA del dosier del worker (`compose_context`).
  · Y aun así seguía saliendo, porque **la regla estaba escrita en tres sitios y aplicada en uno**: el bloque
    pasivo la tenía desde la auditoría del 2026-07-14, el dosier la ganó el 2026-08-21… y ESTE —el recall activo,
    el que corre CADA TURNO— no la tenía. Medido con las dos correcciones ya dentro:

        Puede que venga a cuento (de tu memoria):
        · Weather in Soria now: 14.5C, parcialmente nublado.   ← el volcado del widget
        · Vive en el centro de Madrid.                          ← el hecho del operador

    El volcado del widget POR ENCIMA del slot de perfil.

Es la misma forma que `_next_action` (V2-253) y que el canal de texto (V2-252): **el fallo no fue la regla, fue
tenerla repetida**. Por eso aquí se APLICA la que ya existe (`memory.api.background_slot_off_topic`) en vez de
escribir una cuarta copia.
"""
import pytest

from memory.api import background_slot_off_topic as regla
from nucleo.flash import prompt as fp


class _Mem(dict):
    pass


def _pildoras():
    return [
        _Mem(level="mid", kind="note", slot="meteo-soria:weather:soria",
             text="Weather in Soria now: 14.5C, parcialmente nublado.", id=1),
        _Mem(level="long", kind="profile", slot="operator.location",
             text="Vive en el centro de Madrid.", id=2),
    ]


@pytest.fixture
def memoria(monkeypatch):
    from memory import api

    def _query(prompt, **kw):
        return {"state": {}, "memories": _pildoras(), "ids": [1, 2]}

    monkeypatch.setattr(api, "query", _query, raising=False)


# ── el caso medido ───────────────────────────────────────────────────────────────────────────────────────────

def test_el_volcado_del_widget_NO_sale_en_un_encargo_de_otro_tema(memoria):
    bloque, _ids = fp.compose_recall("busca un fontanero que venga hoy")
    assert "Madrid" in bloque, "el hecho del operador tiene que seguir estando"
    assert "Soria" not in bloque, "el parte meteorológico de otra ciudad decidía la ciudad del encargo"


def test_pero_SI_el_operador_lo_nombra_entra(memoria):
    """La promesa de la auditoría de 2026-07-14: estas píldoras siguen alcanzables ante una pregunta explícita.
    Sin este caso, «filtrar el fondo» se satisfaría borrándolas siempre y el widget dejaría de servir para nada."""
    bloque, _ids = fp.compose_recall("¿qué tiempo hace en Soria?")
    assert "Soria" in bloque


def test_un_hecho_del_OPERADOR_nunca_se_filtra(memoria):
    bloque, _ids = fp.compose_recall("¿dónde vivo?")
    assert "Madrid" in bloque


# ── que sea LA MISMA regla, no una cuarta copia ──────────────────────────────────────────────────────────────

def test_aqui_se_APLICA_la_regla_que_ya_existe():
    """GUARDA DE FUENTE, y es el corazón: el fallo no fue la regla, fue tenerla repetida. Una cuarta copia
    volvería a separarse y habría que descubrirlo con otro fallo en vivo."""
    import inspect
    src = inspect.getsource(fp.compose_recall)
    assert "background_slot_off_topic" in src
    assert "meteo-soria" not in src, "esto no puede nombrar un widget concreto: la regla es genérica"


def test_la_regla_sigue_teniendo_UNA_casa():
    """Si alguien la vuelve a copiar, este caso no lo caza — pero sí caza que esta superficie deje de usar la
    compartida, que es la mitad que está en mi mano."""
    import inspect
    assert "def background_slot_off_topic" in inspect.getsource(
        __import__("memory.api", fromlist=["x"]))


def test_si_la_regla_no_esta_se_enseña_de_MAS_y_nunca_de_menos(monkeypatch, memoria):
    """Fail-soft con dirección: esto corre en el camino caliente de CADA turno. Si la importación fallara, la
    salida correcta es enseñar de más —memoria de sobra— y no quedarse sin recall."""
    import inspect
    src = inspect.getsource(fp.compose_recall)
    assert "except Exception" in src and "nunca de menos" in src


# ── y la regla, en sus tres formas ───────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("slot,peticion,fuera", [
    ("meteo-soria:weather:soria", "busca un fontanero", True),
    ("meteo-soria:weather:soria", "el tiempo en Soria", False),
    ("operator.location", "busca un fontanero", False),
    ("", "busca un fontanero", False),
])
def test_la_regla_compartida_dice_lo_que_creemos(slot, peticion, fuera):
    assert regla(slot, peticion) is fuera
