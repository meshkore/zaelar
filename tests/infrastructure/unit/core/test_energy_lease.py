"""ARRIENDO DE ENERGÍA (ADR-0005) — el techo que la máquina se vigila sola.

Lo que se prueba no es que la resta reste. Es lo que el diseño existe para garantizar: que sin enlace
con la nube esta máquina NO gasta sin techo, y que el fusible no le quite el control al operador.
"""
import time

import pytest

from nucleo import energy_lease


@pytest.fixture(autouse=True)
def limpio(monkeypatch):
    energy_lease._reset_for_tests()
    monkeypatch.setattr(energy_lease, "_persist", lambda: None)
    yield
    energy_lease._reset_for_tests()


def _con_arriendo(monkeypatch, granted=100.0, ttl=1800.0):
    monkeypatch.setattr(energy_lease, "enabled", lambda: True)
    energy_lease._loaded = True
    energy_lease._state.update({"lease_id": "L1", "granted": granted, "spent": 0.0,
                                "expires_at": time.time() + ttl, "at": time.time()})


def test_self_host_no_tiene_arriendo_ni_lo_necesita(monkeypatch):
    """Sin cuenta de nube: siempre permitido, cero estado, cero red. Quien se auto-hospeda paga sus
    propias APIs y no le arrienda energía nadie."""
    monkeypatch.setattr(energy_lease, "enabled", lambda: False)
    assert energy_lease.allowed() is True
    energy_lease.note_spend(999999)
    assert energy_lease.allowed() is True
    assert energy_lease.snapshot() == {"leased": False}


def test_sin_arriendo_una_cuenta_de_nube_NO_puede_gastar(monkeypatch):
    """Fail-closed. La ausencia de arriendo es el estado CERRADO, no «adelante hasta que alguien diga
    lo contrario» — que es el `guarded-until-configured` que costó nueve días de nube abierta."""
    monkeypatch.setattr(energy_lease, "enabled", lambda: True)
    energy_lease._loaded = True
    assert energy_lease.allowed() is False


def test_gastar_por_debajo_del_techo_no_toca_la_red(monkeypatch):
    """El punto entero del diseño: en régimen, gastar es una resta. Si esto llamara a la nube, la
    latencia que el arriendo existe para evitar estaría de vuelta."""
    _con_arriendo(monkeypatch)
    llamadas = []
    monkeypatch.setattr(energy_lease, "_schedule", lambda c: (llamadas.append(1), c.close()))
    energy_lease.note_spend(10.0)
    assert energy_lease.remaining() == pytest.approx(90.0)
    assert energy_lease.allowed() is True
    assert not llamadas


def test_a_la_mitad_se_pide_renovacion_ANTES_de_quedarse_sin_nada(monkeypatch):
    _con_arriendo(monkeypatch)
    pedidas = []
    monkeypatch.setattr(energy_lease, "_schedule", lambda c: (pedidas.append(1), c.close()))
    energy_lease.note_spend(50.0)
    assert pedidas, "no se pidió renovación al 50%: llegaría tarde"
    assert energy_lease.allowed() is True, "el arriendo actual sigue sirviendo mientras se renueva"


def test_agotarse_PARA_de_verdad(monkeypatch):
    """Sin esto, «reactivo» es solo esperar que la nube conteste. El fusible es lo que acota el daño."""
    _con_arriendo(monkeypatch)
    parado = []
    monkeypatch.setattr(energy_lease, "_schedule", lambda c: c.close())
    monkeypatch.setattr(energy_lease, "_blow_fuse", lambda: parado.append(1))
    energy_lease.note_spend(100.0)
    assert energy_lease.allowed() is False
    assert parado


def test_un_arriendo_caducado_no_sirve_aunque_le_quede_saldo(monkeypatch):
    """La caducidad es la otra mitad del techo: una Machine dormida meses no puede despertar y gastar
    contra una autorización de otra época."""
    _con_arriendo(monkeypatch, ttl=-1)
    assert energy_lease.expired() is True
    assert energy_lease.allowed() is False


def test_pasarse_no_deja_el_restante_en_negativo(monkeypatch):
    """Pasarse es NORMAL —una operación en vuelo puede cruzar el límite— y está presupuestado por el
    margen del emisor. Lo que importa es que a partir de ahí no se empieza nada nuevo."""
    _con_arriendo(monkeypatch, granted=10.0)
    monkeypatch.setattr(energy_lease, "_schedule", lambda c: c.close())
    monkeypatch.setattr(energy_lease, "_blow_fuse", lambda: None)
    energy_lease.note_spend(25.0)
    assert energy_lease.remaining() == 0.0
    assert energy_lease.allowed() is False


def test_contar_jamas_tumba_el_turno_que_lo_disparo(monkeypatch):
    _con_arriendo(monkeypatch)

    def revienta():
        raise RuntimeError("kv caído")

    monkeypatch.setattr(energy_lease, "_persist", revienta)
    energy_lease.note_spend(1.0)          # no debe lanzar


def test_al_renovar_se_reanuda_SOLO_lo_que_paramos_nosotros(monkeypatch):
    """Asimetría deliberada, heredada de V2-092: si paró el OPERADOR, no se toca. Encender algo que una
    persona apagó a mano es de las cosas que más desconfianza generan."""
    from nucleo import runstate

    arrancados = []
    monkeypatch.setattr(energy_lease, "_schedule", lambda c: (arrancados.append(1), c.close()))
    monkeypatch.setattr(runstate, "stopped", lambda: True)

    monkeypatch.setattr(runstate, "snapshot", lambda: {"src": "operator"})
    energy_lease._maybe_resume()
    assert not arrancados, "se reanudó una parada del OPERADOR"

    monkeypatch.setattr(runstate, "snapshot", lambda: {"src": energy_lease.STOP_SRC})
    energy_lease._maybe_resume()
    assert arrancados, "no se reanudó lo que paramos nosotros por energía"


def test_arrancando_no_es_agotado(monkeypatch):
    """Al arrancar el arriendo se pide como tarea; una operación que llegue antes NO puede parar el
    agente para que se rearranque un segundo después. Ese parpadeo no protege de nada."""
    monkeypatch.setattr(energy_lease, "enabled", lambda: True)
    energy_lease._loaded = True
    energy_lease._renewing = True                      # petición en vuelo, sin arriendo todavía
    parado = []
    monkeypatch.setattr(energy_lease, "_schedule", lambda c: (parado.append(1), c.close()))
    energy_lease._blow_fuse()
    assert not parado


def test_pero_agotado_de_verdad_SI_para(monkeypatch):
    """El guard anterior no puede convertirse en una puerta abierta: con arriendo concedido y gastado,
    el fusible salta igual."""
    from nucleo import runstate
    monkeypatch.setattr(energy_lease, "enabled", lambda: True)
    energy_lease._loaded = True
    energy_lease._renewing = True                      # incluso renovando…
    energy_lease._state.update({"granted": 10.0, "spent": 10.0})   # …pero YA tuvo arriendo y lo gastó
    parado = []
    monkeypatch.setattr(runstate, "stopped", lambda: False)
    monkeypatch.setattr(energy_lease, "_schedule", lambda c: (parado.append(1), c.close()))
    energy_lease._blow_fuse()
    assert parado


def test_el_fusible_arranca_un_reintento_o_seria_una_trampa(monkeypatch):
    """Sin esto el fusible es irreversible en la práctica: la renovación se dispara al GASTAR, y parados
    no se gasta — así que recargar el saldo no despertaría nunca a la máquina. Se encontró desplegándolo.
    """
    from nucleo import runstate
    monkeypatch.setattr(energy_lease, "enabled", lambda: True)
    energy_lease._loaded = True
    energy_lease._state.update({"granted": 10.0, "spent": 10.0})
    monkeypatch.setattr(runstate, "stopped", lambda: False)
    monkeypatch.setattr(energy_lease, "_schedule", lambda c: c.close())
    arrancado = []
    monkeypatch.setattr(energy_lease, "_start_retry", lambda: arrancado.append(1))
    energy_lease._blow_fuse()
    assert arrancado, "el fusible saltó sin dejar forma de volver"
