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


# ── Y que los dos platós avancen, no solo uno (2026-08-28) ──────────────────────────────────────────────────
def test_los_dos_platos_se_alternan_dentro_de_cada_grupo():
    """El operador pidió medir US **y** ES. La prioridad de la rotación («rotos primero») es lo valioso y no
    se toca; lo que fallaba es que dentro de cada grupo el orden salía del diccionario del marcador y los
    `__us` quedaban en bloque — medido: el primer caso US estaba en la **posición 21** de 132, a unas dos
    horas y tres cuartos de plató. Un bucle que corre toda la noche sin tocar media lista no está midiendo
    esa mitad, aunque la tenga escrita."""
    got = S.intercala(["a__es", "b__es", "c__es", "x__us", "y__us"])
    assert got == ["a__es", "x__us", "b__es", "y__us", "c__es"]


def test_el_mas_largo_termina_de_tirar_solo():
    assert S.intercala(["a__es", "b__es", "c__es"]) == ["a__es", "b__es", "c__es"]
    assert S.intercala(["x__us", "y__us"]) == ["x__us", "y__us"]
    assert S.intercala([]) == []


def test_se_alterna_pero_NO_se_baraja():
    """Barajar haría que dos vueltas seguidas no se puedan comparar, y la rotación es justo lo que las hace
    comparables. El orden relativo dentro de cada plató tiene que sobrevivir intacto."""
    ids = [f"{c}__es" for c in "abcde"] + [f"{c}__us" for c in "vwxyz"]
    got = S.intercala(ids)
    assert [x for x in got if x.endswith("__es")] == [f"{c}__es" for c in "abcde"]
    assert [x for x in got if x.endswith("__us")] == [f"{c}__us" for c in "vwxyz"]
    assert sorted(got) == sorted(ids), "no se pierde ni se duplica ningún caso"


def test_la_prioridad_sigue_mandando_DENTRO_de_cada_plato():
    """Reescrito 2026-08-28, NO volteado. La propiedad —la prioridad manda— es la misma; lo que cambió es
    dónde significa algo.

    Antes se alternaba dentro de cada grupo (`intercala(rotos) + intercala(nunca) + intercala(buenos)`), y
    medido en las cuatro primeras horas del 24/7 eso dio **25 rondas ES contra 7 US**: ES tiene más casos
    rotos, así que al agotar los US del grupo «rotos» quedaban trece ES seguidos antes de llegar al grupo
    «nunca medidos», que es donde viven los 52 US sin tocar.

    Ahora cada plató lleva su cola completa (rotos → nunca → buenos) y se alternan turno a turno. Lo que se
    sacrifica es que un roto de un plató vaya antes que un nunca-medido del OTRO — una comparación que no
    significa nada, porque son dos productos midiéndose en paralelo, no una sola lista.
    """
    from pathlib import Path
    src = Path("tests/use_cases/e2e/agent/supervisor.py").read_text(encoding="utf-8")
    assert "return intercala(cola_es + cola_us)" in src
    assert src.index("rotos + nunca + buenos") < src.index("return intercala(cola_es + cola_us)")


def test_cada_plato_lleva_su_PROPIA_cola_de_prioridad():
    """Intercalar dentro de cada grupo no bastaba, y se vio en las cifras: **25 rondas ES contra 7 US** en las
    cuatro primeras horas del plató 24/7.

    La causa: ES tiene muchos más casos rotos, así que tras agotar los US del grupo «rotos» quedaban trece ES
    seguidos ANTES de que empezara el grupo «nunca medidos» — que es donde viven los 52 casos US que nadie ha
    tocado. La prioridad se respetaba y el operador seguía sin datos de US.

    Ahora cada plató recorre rotos → nunca → buenos por su cuenta y se alternan turno a turno: la prioridad
    sigue intacta DENTRO de cada locale, que es donde significa algo.
    """
    from pathlib import Path
    src = Path("tests/use_cases/e2e/agent/supervisor.py").read_text(encoding="utf-8")
    assert "cola_es = [x for x in rotos + nunca + buenos if not x.endswith" in src
    assert "return intercala(cola_es + cola_us)" in src


def test_un_ROTO_de_su_plato_sigue_yendo_antes_que_un_BUENO_del_mismo():
    """La prioridad no se sacrifica por alternar: se sacrifica que un roto de un plató vaya antes que un
    nunca-medido del OTRO, que es una comparación que no significa nada."""
    got = S.intercala(["roto__es", "nunca__es", "bueno__es", "roto__us", "nunca__us"])
    solo_es = [x for x in got if not x.endswith("__us")]
    assert solo_es == ["roto__es", "nunca__es", "bueno__es"]
    solo_us = [x for x in got if x.endswith("__us")]
    assert solo_us == ["roto__us", "nunca__us"]
