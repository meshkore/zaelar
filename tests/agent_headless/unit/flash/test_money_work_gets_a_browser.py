"""V2-148 (`pay-known-bill__es`) — todo pago iba a un worker SIN navegador.

Medido sobre las frases del propio caso, antes de tocar nada:

    dispatch._classify_kind("Paga la factura de la luz de este mes antes del día 5.")   → "generic"
    dispatch._classify_kind("paga la factura de Endesa de este mes")                    → "generic"
    dispatch._classify_kind("paga la factura de la luz en la web de Endesa")            → "generic"

Las tres a `generic`, incluso después de que el operador nombrara el proveedor y dijera dónde la paga. Yo mismo
lo había dejado abierto DOS veces (V2-141, V2-144) con la nota «el destino de un pago es la web del proveedor
CONCRETO, no un sitio de confianza común, así que no es la misma solución que una categoría del catálogo». Era
cierto — y era la conclusión equivocada: no necesita entrada de catálogo ninguna, necesita NAVEGADOR.

Y el daño no es «no paga» (imposible sin cuenta real, y el caso no lo penaliza): sin navegador la tarea no puede
llegar al muro de login, así que el sistema pierde la única respuesta honesta que tenía — «llego al login de
Endesa y necesito que entres tú» — y el turno rellena el hueco narrando. Es el argumento que V2-126 escribió para
Netflix y V2-138 repitió para el resto de proveedores, por tercera vez.
"""
from __future__ import annotations

import pytest

from nucleo import dispatch
from nucleo.flash import prompt
from nucleo.flash import router_guards as g


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    from memory import db as memdb
    from memory import embeddings as mememb
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    mememb.reset()
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()
    mememb.reset()


@pytest.mark.parametrize("text", [
    "Paga la factura de la luz de este mes antes del día 5.",   # the case's opening, verbatim
    "paga la factura de Endesa de este mes",
    "paga la factura de la luz en la web de Endesa",
    "renueva mi cuota del gimnasio",
    "cancela la suscripción de Movistar",                       # a provider in no list of ours
])
def test_a_money_or_commitment_errand_gets_a_browser(text):
    assert g.money_work_needs_a_browser(text) is True
    assert dispatch._classify_kind(text) == "web"


@pytest.mark.parametrize("text", [
    "pon la factura en pantalla",          # the screen, not the world
    "borra la factura de la agenda",       # a data-op on his own list
    "quita la cuota de la lista",
    "recuérdame pagar la factura el día 5",  # a note; the reminder clipping holds
    "cierra el widget de la factura",
])
def test_and_these_carry_a_money_word_without_being_an_errand(text):
    assert g.money_work_needs_a_browser(text) is False
    assert dispatch._classify_kind(text) != "web"


@pytest.mark.parametrize("text,kind", [
    ("hazme un informe sobre coches eléctricos para ciudad", "generic"),
    ("móntame un widget de entrenamientos", "code"),
    ("pon música en Spotify", "generic"),
    ("manda un whatsapp a Ana", "generic"),
    ("conecta mi Spotify", "generic"),
])
def test_the_other_kinds_are_untouched(text, kind):
    """The new branch goes AFTER the existing ones on purpose: a named site or a transactional category has
    already resolved by then, and a report must not become a browser task."""
    assert dispatch._classify_kind(text) == kind


def test_a_limit_you_admitted_stays_admitted(fresh_db):
    """Three times in one conversation: «no tengo acceso a tu email» (turn 6) and two turns later «voy a buscar
    tu factura de Endesa en tu email». The operator had to correct it both times."""
    system, _ = prompt.build_flash_system()
    assert "un LÍMITE que hayas reconocido sigue en pie" in system
    assert "me paro en el login, entra tú" in system
