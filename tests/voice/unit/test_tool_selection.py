"""Selección PROGRESIVA de tools — V2-096 Fase 2, nodo 3.10.

Peticón del operador: «cuando alguien dice "hola, ¿qué tal?" no le vamos a mandar todos los widgets, todas las
tools… ir encaminando la dirección».

Lo que estos tests protegen, por orden de importancia:
  1. **Que recortar no deje un turno sin salida.** Medido sobre los 14 casos del nodo 2.13: cero casos se quedan sin
     ninguna tool aceptable, y el catálogo baja un 51,4% de chars.
  2. **Que exista la escotilla.** Recuperar no es comprender: cuando se recorta, el modelo tiene que poder pedir la
     familia que le falta (`need_capability`) y provocar UN segundo viaje medible. Sin ella, una recuperación
     equivocada es una capacidad negada en silencio — el fallo que de verdad rompe una conversación.
  3. **Que las familias imprescindibles no se toquen nunca**: `core`, `web` y `memory` sirven turnos que no se
     anuncian ni en el estado ni en las palabras («¿cuánto cuesta la entrada?»).
"""
from __future__ import annotations

import json

import pytest

from nucleo.flash import router, tool_selection as ts
from tests.agent_headless.e2e.prompt_cost.bench_fast_model import CASES

FULL = router.TOOLS


def _names(tools):
    return {(t.get("function") or {}).get("name") for t in tools}


def test_ningun_caso_real_se_queda_sin_tool_aceptable():
    """El invariante que decide si esto se puede desplegar. Semántica del banco: basta con que quede ALGUNA de las
    aceptadas (y si el caso no espera ninguna, no hace falta ninguna)."""
    malos = []
    for name, text, expect, _forbid in CASES:
        got = _names(ts.select(FULL, turn_text=text)[0])
        if expect and not (expect & got):
            malos.append((name, sorted(expect), sorted(got)))
    assert not malos, f"casos sin ninguna tool aceptable tras recortar: {malos}"


def test_el_recorte_ahorra_de_verdad():
    """Si no ahorra, todo este riesgo no se paga. Medido: −51,4% sobre los 14 casos."""
    antes = sum(len(json.dumps(FULL)) for _ in CASES)
    despues = sum(len(json.dumps(ts.select(FULL, turn_text=t)[0])) for _, t, _, _ in CASES)
    ahorro = (antes - despues) / antes
    assert ahorro > 0.30, f"solo ahorra {ahorro:.1%} — no compensa el riesgo de enrutado"


@pytest.mark.parametrize("fam", sorted(ts.ALWAYS))
def test_las_familias_imprescindibles_nunca_se_recortan(fam):
    got = _names(ts.select(FULL, turn_text="hola qué tal")[0])
    for n in router.FAMILIES[fam]:
        if n in _names(FULL):
            assert n in got, f"{n} ({fam}) se recortó en un turno de charla"


def test_charla_no_arrastra_widgets_ni_media():
    """El caso literal del operador."""
    sel, rep = ts.select(FULL, turn_text="hola, ¿qué tal todo?")
    got = _names(sel)
    assert "widget_data" not in got and "play_music" not in got
    assert len(sel) < len(FULL) and rep["omitted"]


def test_la_escotilla_aparece_SOLO_si_se_recorto():
    sel, _ = ts.select(FULL, turn_text="hola")
    assert "need_capability" in _names(sel), "se recortó y no se ofreció salida"
    sel2, _ = ts.select(FULL, turn_text="hola",
                        force={"widgets", "media", "workers", "cluster", "messaging"})
    assert "need_capability" not in _names(sel2), "sin recorte no hay nada que pedir"
    assert len(sel2) == len(FULL)


def test_lo_que_el_operador_tiene_DELANTE_entra_sin_mirar_palabras():
    """Capa de ESTADO (V2-085): con un widget abierto, su familia entra aunque el turno no la nombre."""
    got = _names(ts.select(FULL, turn_text="y eso qué es", open_widgets=["agenda"])[0])
    assert "widget_data" in got and "show_widget" in got


def test_la_familia_reciente_mantiene_el_hilo():
    """Una conversación que ya iba de música no debería perderla porque el turno siguiente no la nombre
    («la siguiente», «más alto»)."""
    got = _names(ts.select(FULL, turn_text="la siguiente", recent_families=["media"])[0])
    assert "play_music" in got


def test_una_orden_de_parar_conserva_las_tools_de_worker():
    """«para» con un worker vivo es PARAR UN WORKER (precedencia de V2-038). Si el recorte se llevara
    `stop_worker`, el operador no podría parar lo que ha lanzado."""
    got = _names(ts.select(FULL, turn_text="para eso")[0])
    assert "stop_worker" in got


def test_el_kill_switch_devuelve_el_catalogo_entero(monkeypatch):
    """Un cambio que toca el ENRUTADO tiene que poder apagarse sin desplegar código."""
    monkeypatch.setenv("ZAELAR_TOOL_SELECTION", "0")
    sel, rep = ts.select(FULL, turn_text="hola")
    assert len(sel) == len(FULL) and rep["selection"] == "off"


def test_families_used_alimenta_la_capa_reciente():
    assert ts.families_used(["play_music"]) == {"media"}
    assert ts.families_used(["widget_data", "show_widget"]) == {"widgets"}
    assert ts.families_used(["no_existe"]) == set()


def test_toda_tool_del_catalogo_tiene_familia():
    """Una tool sin familia se colaría SIEMPRE (el selector la deja pasar por defecto, que es el lado seguro) y
    nunca se podría recortar. Es deuda silenciosa: mejor que salte aquí."""
    huerfanas = _names(FULL) - set(ts._family_of)
    assert not huerfanas, f"tools sin familia en router.FAMILIES: {sorted(huerfanas)}"
