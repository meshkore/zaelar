"""PROGRESSIVE tool selection — V2-096 Phase 2, node 3.10.

Operator request: «when someone says "hello, how are you?" we are not going to send them every widget, every
tool… gradually steer the direction».

What these tests protect, in order of importance:
  1. **That trimming does not leave a turn with no way forward.** Measured across the 14 cases from node 2.13: zero
     cases are left without any acceptable tool, and the catalog drops by 51.4% of its characters.
  2. **That the escape hatch exists.** Recovery is not understanding: when trimming occurs, the model must be able to
     request the missing family (`need_capability`) and trigger ONE measurable second trip. Without it, an incorrect
     recovery is a capability silently denied — the failure that truly breaks a conversation.
  3. **That essential families are never touched**: `core`, `web`, and `memory` serve turns that are announced
     neither by the state nor by the words («how much does the ticket cost?»).
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
    """The invariant that determines whether this can be deployed. Test-bank semantics: it is enough for ANY of the
    accepted tools to remain (and if the case expects none, none is needed)."""
    malos = []
    for name, text, expect, _forbid in CASES:
        got = _names(ts.select(FULL, turn_text=text)[0])
        if expect and not (expect & got):
            malos.append((name, sorted(expect), sorted(got)))
    assert not malos, f"casos sin ninguna tool aceptable tras recortar: {malos}"


def test_el_recorte_ahorra_de_verdad():
    """If it does not save anything, all this risk is not worth taking. Measured: −51.4% across the 14 cases."""
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
    """The operator's literal case."""
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
    """STATE layer (V2-085): with an open widget, its family is included even if the turn does not name it."""
    got = _names(ts.select(FULL, turn_text="y eso qué es", open_widgets=["agenda"])[0])
    assert "widget_data" in got and "show_widget" in got


def test_la_familia_reciente_mantiene_el_hilo():
    """A conversation that was already about music should not lose it because the next turn does not name it
    («the next one», «louder»)."""
    got = _names(ts.select(FULL, turn_text="la siguiente", recent_families=["media"])[0])
    assert "play_music" in got


def test_una_orden_de_parar_conserva_las_tools_de_worker():
    """«stop» with a live worker means STOP A WORKER (V2-038 precedence). If trimming removed
    `stop_worker`, the operator would not be able to stop what they launched."""
    got = _names(ts.select(FULL, turn_text="para eso")[0])
    assert "stop_worker" in got


def test_el_kill_switch_devuelve_el_catalogo_entero(monkeypatch):
    """A change that affects ROUTING must be able to be switched off without deploying code."""
    monkeypatch.setenv("ZAELAR_TOOL_SELECTION", "0")
    sel, rep = ts.select(FULL, turn_text="hola")
    assert len(sel) == len(FULL) and rep["selection"] == "off"


def test_families_used_alimenta_la_capa_reciente():
    assert ts.families_used(["play_music"]) == {"media"}
    assert ts.families_used(["widget_data", "show_widget"]) == {"widgets"}
    assert ts.families_used(["no_existe"]) == set()


def test_toda_tool_del_catalogo_tiene_familia():
    """A tool without a family would ALWAYS slip through (the selector lets it pass by default, which is the safe
    side) and could never be trimmed. It is silent debt: better for it to be caught here."""
    huerfanas = _names(FULL) - set(ts._family_of)
    assert not huerfanas, f"tools sin familia en router.FAMILIES: {sorted(huerfanas)}"
