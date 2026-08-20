"""La captura forense de un turno tiene que guardar la parte que CAMBIA (V2-195).

`observer.turn_detail` existe para responder «¿qué vio el modelo?» — su propio docstring lo dice: «¿por qué
re-escaló en un turno ambiente? = mirar qué ventana/prompt vio». Y guardaba `system[:8000]` de un prompt que
mide ~19.000 caracteres.

La persona estática va al principio y **`prompt.live_state()` se compone al FINAL**, así que lo que se cortaba
era exactamente la mitad que cambia cada turno: la hora, las tareas de fondo, el bloque del navegador, un
muro, una confirmación pendiente.

El 2026-08-20 ese truncamiento hizo que cinco turnos de una corrida medida parecieran no tener nunca el bloque
del navegador — con el navegador emitiendo 74 eventos en esa misma corrida. Tres pasos dentro de concluir que
una noche entera de arreglos era invisible para el modelo, cuando lo único que faltaba era el artefacto. Un
diagnóstico que trunca justo la evidencia que le piden es peor que no tenerlo: parece una respuesta.
"""
from __future__ import annotations

from voice import observer


def _prompt(head: str = "PERSONA", tail: str = "ESTADO", filler: int = 30_000) -> str:
    return head + ("x" * filler) + tail


def test_the_TAIL_survives_because_that_is_where_the_live_state_goes():
    ex = observer._prompt_excerpt(_prompt())
    assert ex.endswith("ESTADO")


def test_and_the_head_too_because_the_rules_live_there():
    assert observer._prompt_excerpt(_prompt()).startswith("PERSONA")


def test_and_the_gap_is_NAMED_so_a_hole_is_not_read_as_an_absence():
    """Es la lección entera del hallazgo: leí un hueco como una ausencia. Si el extracto dice cuánto falta y
    dónde está el estado, nadie más lo hace."""
    ex = observer._prompt_excerpt(_prompt())
    assert "OMITIDOS" in ex and "el estado vivo va al final" in ex


def test_a_short_prompt_is_kept_whole():
    assert observer._prompt_excerpt("corto") == "corto"


def test_and_a_REAL_turn_keeps_its_browser_block():
    """La comprobación que importa, con el prompt de verdad y no con relleno."""
    from nucleo.flash import prompt as _p
    from widgets.navegador import tasks

    tasks._tasks.clear()
    tid = tasks.create("Reservar noche en el hotel")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url="chrome-error://chromewebdata/")
    try:
        system, _ = _p.build_flash_system(turn_text="¿lo tienes ya?")
        ex = observer._prompt_excerpt(system)
        assert "NAVEGADOR" in ex
        assert "· MURO: " in ex
    finally:
        tasks._tasks.clear()
