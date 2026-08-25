"""El juez recibe los dos hechos que le impiden acusar al producto de algo que pasó FUERA de él.

Medido en `find-concert-tickets__es` (2026-08-25 12:25). Zaelar dijo, con esas palabras, que se había quedado
sin cuota en el proveedor de sus procesos de fondo. El juez leyó la hoja vacía y escribió como bloqueador nº1
«la incapacidad de zaelar para reconocer y reportar fallos técnicos explícitos (cuota agotada)» — exactamente lo
contrario de lo ocurrido — y puso `resultado 1 · mecanismo 2`.

El informe de mecanismo es la fuente de verdad sobre el texto (docstring de `judge.py`), así que si el hecho no
está EN el informe el juez no puede hacer otra cosa que inferirlo del transcript. Los dos hechos:

  · sin CUOTA para lanzar workers → nuestra factura
  · un RESET ajeno a mitad de ronda → cierra las tarjetas y deja la pestaña «cancelada» sin cancelar nada
"""
from tests.use_cases.e2e.agent.judge import mechanism_facts


def test_sin_los_hechos_no_dice_nada_de_ellos():
    txt = mechanism_facts({"worker_health": {"spawned": 1, "ok": 1}})
    assert "NO HABÍA CUOTA" not in txt
    assert "RESETEÓ EL MOTOR" not in txt


def test_la_cuota_agotada_llega_al_juez_NOMBRADA():
    txt = mechanism_facts({"provider_exhausted": {"deaths": 3, "asleep": 0,
                                                  "providers": ["licencia-claude"], "reset_at": 0}})
    assert "NO HABÍA CUOTA" in txt
    assert "licencia-claude" in txt
    assert "3" in txt


def test_y_con_la_INSTRUCCION_de_no_puntuarlo_contra_el_producto():
    """El hecho suelto no basta: el juez ya tenía el transcript diciéndolo y aun así lo puntuó. La línea le dice
    qué HACER con el hecho, que es lo que el resto de esta función hace con todos los demás."""
    txt = mechanism_facts({"provider_exhausted": {"deaths": 4, "asleep": 0, "providers": [], "reset_at": 0}})
    low = txt.lower()
    assert "no bajes" in low
    assert "honestidad" in low


def test_la_cadena_dormida_cuenta_aunque_no_muera_nadie():
    """Desde V2-314 el dispatcher se niega a lanzar cuando toda la cadena duerme: cero muertes, cero ronda."""
    txt = mechanism_facts({"provider_exhausted": {"deaths": 0, "asleep": 2, "providers": [], "reset_at": 0}})
    assert "NO HABÍA CUOTA" in txt
    assert "cooldown" in txt.lower()


def test_el_reset_ajeno_llega_CON_SU_SEGUNDO():
    """El cuándo es la mitad del hecho: a los 12 s tira la ronda entera, a los 400 s puede haber caído después
    de la entrega que importaba."""
    txt = mechanism_facts({"resets_during_round": {"n": 1, "at_s": [12.5]}})
    assert "RESETEÓ EL MOTOR" in txt
    assert "12.5s" in txt


def test_y_explica_POR_QUE_una_pestaña_sale_cancelada_sin_que_nadie_cancele():
    txt = mechanism_facts({"resets_during_round": {"n": 2, "at_s": [30.0, 90.0]}})
    low = txt.lower()
    assert "tarjeta" in low and "cancelada" in low
