"""Un caso de San Francisco no se mide con el plató de Madrid.

`--lab es` sobre un caso `__us` NO falla: mide. Y lo que mide es a Marc, de Madrid, conduciendo un encargo de
San Francisco en castellano dentro de un brief inglés. Un tester que se contradice a sí mismo no mide el
producto, mide el arnés — y la ronda sale VERDE de infraestructura, así que el resultado entra al marcador
como si fuera un veredicto sobre el producto. Misma familia que los 19 escenarios US que el 2026-08-27
contestaban con realidad española, e invisible desde fuera por el mismo motivo.

El defecto vivía en dos sitios y es UNO:
  · el supervisor —el bucle que va a correr 24 h seguidas— llamaba a `una_ronda(esc)` sin plató, así que se
    quedaba el `es` por defecto para TODO, incluidos los `__us`.
  · `run.py` no lo impedía, así que arreglar solo el supervisor deja el mismo error a un `--lab` a mano.

La negativa es fail-closed a propósito: una medición con la persona equivocada es peor que ninguna, porque la
que no existe no engaña a nadie.
"""
from __future__ import annotations

from dataclasses import dataclass

from tests.use_cases.e2e.agent import supervisor as S
from tests.use_cases.e2e.agent.run import wrong_lab_refusal


@dataclass
class _Caso:
    id: str
    locale: str


def test_el_sufijo_del_id_dice_el_plato():
    assert S.plato_de("cheapest-monitor__us") == "us"
    assert S.plato_de("cheapest-monitor__es") == "es"
    assert S.plato_de("hotel-under-15-days") == "es", "sin sufijo, el plató de siempre"


def test_el_supervisor_lo_pasa_de_verdad(monkeypatch):
    """No basta con que la función exista: `main()` tenía que dejar de llamar sin plató."""
    vistos: list[tuple[str, str]] = []

    def _falsa_ronda(esc, lab="es"):
        vistos.append((esc, lab))
        if len(vistos) >= 2:
            raise KeyboardInterrupt          # corta el bucle infinito del supervisor
        return {}

    monkeypatch.setattr(S, "rotacion", lambda: ["cheapest-monitor__us", "hotel-under-15-days"])
    monkeypatch.setattr(S, "una_ronda", _falsa_ronda)
    monkeypatch.setattr(S.time, "sleep", lambda *_: None)
    monkeypatch.setattr(S, "_recargar_si_cambie", lambda *_: None)
    try:
        S.main()
    except KeyboardInterrupt:
        pass
    assert vistos == [("cheapest-monitor__us", "us"), ("hotel-under-15-days", "es")]


def test_el_plato_equivocado_se_niega():
    msg = wrong_lab_refusal("es", [_Caso("cheapest-monitor__us", "us")])
    assert msg and "cheapest-monitor__us" in msg and "--lab es" in msg


def test_el_plato_correcto_pasa():
    """La mitad de sensibilidad: sin esto, «niega el cruce» y «lo niega todo» pasan igual."""
    assert wrong_lab_refusal("us", [_Caso("cheapest-monitor__us", "us")]) == ""
    assert wrong_lab_refusal("es", [_Caso("hotel-under-15-days", "es")]) == ""


def test_una_tanda_mixta_se_niega_entera_y_los_nombra():
    """El caso real de la rotación: la lista trae de los dos y hay que ver CUÁLES sobran."""
    casos = [_Caso("a__us", "us"), _Caso("b", "es"), _Caso("c__us", "us")]
    msg = wrong_lab_refusal("es", casos)
    assert "a__us" in msg and "c__us" in msg and "2 caso" in msg
    assert " b," not in msg and "b." not in msg, "el que sí encaja no se acusa"


def test_un_sandbox_no_tiene_persona_y_no_es_asunto_de_esto():
    """Sin `--lab` no hay agente persistente ni perfil que contradecir: la negativa no aplica."""
    assert wrong_lab_refusal("", [_Caso("cheapest-monitor__us", "us")]) == ""
