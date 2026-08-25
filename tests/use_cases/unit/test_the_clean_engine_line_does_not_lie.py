"""V2-328 — «motor limpio» miraba dos señales de tres, y afirmaba lo contrario de lo que pasaba.

`probe_client.settle_after_reset()` comprueba las sesiones de worker (`/api/tasks`) y las tarjetas del canvas.
Le faltaba la tercera: **una pestaña del NAVEGADOR es un registro distinto**, y puede seguir conduciendo sin
sesión de worker viva y sin tarjeta abierta.

MEDIDO EL 2026-08-25, y lo causé yo. Maté una tanda con `hotel-under-15-days` a medias; la siguiente arrancó en
`search-buy-motorcycle__es` y su log dice, literal:

    ▸ motor limpio en 0.0s: sin trabajo vivo ni tarjetas (memoria y estado intactos)

Mientras tanto, entre las 21:06 y las 21:09, el navegador abría `booking.com/hotel/es/eurostars-regina`,
`booking.com/searchresults?ss=Sevilla` y `google.com/travel/search`, y el prompt de esa ronda llevaba
«ibis Budget Sevilla Aeropuerto — 48 €»; «Eurostars Al-Andalus Palace — 55 €».

Los veredictos culparon al PRODUCTO:
  · moto (mecanismo 2): «incapacidad para filtrar ruido estructural (hoteles/recambios)»
  · bici (adaptación 2): «distracción con resultados de otros contextos (hoteles)»

No era el producto perdiendo el foco. Era trabajo nuestro de la tanda anterior, con el arnés afirmando lo
contrario justo en la línea que el operador lee para fiarse de que el caso siguiente se mide solo.

SE MIDE POR ACTIVIDAD, NO POR ESTADO, y eso es deliberado: el estado ya falló una vez de esta forma exacta
(`active_sessions()` sin filtrar antes de V2-115). Un registro con un hueco dice «nada vivo» con la misma cara
que un registro correcto; un hito emitido hace tres segundos no admite interpretación.
"""
import json
import sqlite3
import time

import pytest

from tests.use_cases.e2e.agent import verify as V


@pytest.fixture
def db(tmp_path):
    """Un test unitario nunca mira el plató vivo."""
    p = tmp_path / "obs.db"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, ts_ms INTEGER, topic TEXT, payload TEXT, "
                "cat TEXT, kind TEXT, label TEXT)")

    def add(*, hace_s, label="🏁 hito", text="🌐 abrió https://www.booking.com/searchresults"):
        con.execute("INSERT INTO events (ts_ms, topic, payload, cat, kind, label) VALUES (?,?,?,?,?,?)",
                    (int((time.time() - hace_s) * 1000), "obs", json.dumps({"text": text}),
                     "worker", "navegador", label))
        con.commit()
    return p, add


def test_sin_actividad_de_navegador_no_acusa_a_nadie(db):
    p, add = db
    assert V.browser_still_driving(str(p)) == {"driving": False, "last_s": None, "url": ""}


def test_un_hito_RECIENTE_dice_que_sigue_conduciendo(db):
    p, add = db
    add(hace_s=2)
    r = V.browser_still_driving(str(p))
    assert r["driving"] is True
    assert r["last_s"] < 6
    assert "booking.com" in r["url"], "hay que decir DÓNDE está, o el aviso no sirve para nada"


def test_un_hito_VIEJO_no_lo_dice(db):
    """La sensibilidad: si cualquier rastro antiguo contara, ninguna tanda arrancaría nunca."""
    p, add = db
    add(hace_s=60)
    r = V.browser_still_driving(str(p))
    assert r["driving"] is False
    assert r["last_s"] >= 59


def test_el_umbral_de_silencio_se_puede_ajustar_y_MUERDE(db):
    p, add = db
    add(hace_s=10)
    assert V.browser_still_driving(str(p), quiet_s=6)["driving"] is False
    assert V.browser_still_driving(str(p), quiet_s=20)["driving"] is True


def test_una_db_ilegible_no_tumba_la_tanda(tmp_path):
    """Fail-soft: no poder mirar no es «está sucio». Bloquear una tanda por una lectura fallida costaría más
    que medir un caso con una advertencia."""
    assert V.browser_still_driving(str(tmp_path / "no-existe.db"))["driving"] is False


def test_el_arranque_del_caso_LO_CONSULTA_y_PISA_el_veredicto_limpio():
    """La mitad de cableado, y aquí es la que importa: la señal puede ser perfecta y la línea seguir mintiendo.
    Se comprueba que además de consultarse, MARCA `clean = False` — que es lo que el operador lee."""
    import inspect

    from tests.use_cases.e2e.agent import run as R
    # `_run_batch`, no `_run_scenario`: el reset vive en el bucle del LOTE, antes de cada caso. El primer
    # intento de este test apuntó al sitio equivocado y salió rojo — que es exactamente lo que tiene que hacer
    # un guarda de cableado cuando el cableado no está donde uno cree.
    src = "\n".join(ln for ln in inspect.getsource(R._run_batch).splitlines()
                    if not ln.strip().startswith("#"))
    i = src.find("verifymod.browser_still_driving(")
    assert i > 0, "el arranque del caso dejó de mirar el navegador"
    cola = src[i:i + 400]
    assert 'st["clean"] = False' in cola, "lo consulta y no cambia el veredicto que se imprime"
    j = src.find('if st["clean"]:')
    assert 0 < i < j, "se mira DESPUÉS de imprimir: llegaría tarde"


def test_y_el_aviso_NOMBRA_lo_que_quedó_vivo():
    """Un «no está limpio» sin decir qué quedó vivo obliga a investigar desde cero cada vez."""
    import inspect

    from tests.use_cases.e2e.agent import run as R
    assert 'navegador ACTIVO hace' in inspect.getsource(R._run_batch)
