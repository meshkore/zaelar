"""Bringing the element into view is a COURTESY, not the click (V2-247).

Measured by the harness on 2026-08-21, among the causes V2-236 left open: **three
`ElementHandle.scroll_into_view_if_needed` calls with Exit code 1 in the same worker**, and that worker dead. The
`scroll_into_view_if_needed` call was UNPROTECTED at the start of `_human_click_handle`, so a covered element,
inside a closed accordion, without layout, or detached halfway through would take down the entire action —
even though the click remained perfectly possible: Playwright's `h.click()` performs its own scroll and its own
wait.

Why the courtesy exists: the human click is performed at COORDINATES (Bézier curve + jitter, `_human_move`), so
the element has to be on screen for the mouse to land where the user would see it. When that cannot be done,
the correct response is not to give up: it is to click through the normal route and lose the disguise, not the task.
"""
import asyncio

import pytest

from widgets.navegador import dom


class _Handle:
    """A fake `ElementHandle`. `scroll` and `box` determine what happens to each call."""

    def __init__(self, *, scroll=None, box=None):
        self._scroll, self._box = scroll, box
        self.clicked = False

    async def scroll_into_view_if_needed(self, timeout=None):
        if isinstance(self._scroll, Exception):
            raise self._scroll

    async def bounding_box(self):
        if isinstance(self._box, Exception):
            raise self._box
        return self._box

    async def click(self, timeout=None):
        self.clicked = True


class _Mouse:
    def __init__(self):
        self.clicks = []

    async def move(self, x, y):
        pass

    async def click(self, x, y, delay=None):
        self.clicks.append((x, y))


class _Page:
    def __init__(self):
        self.mouse = _Mouse()


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


# ── the measured case ─────────────────────────────────────────────────────────────────────────────────────────

def test_si_no_se_puede_traer_a_la_vista_SE_CLICA_igual():
    page, h = _Page(), _Handle(scroll=RuntimeError("Timeout 5000ms exceeded"), box=None)
    _run(dom._human_click_handle(page, h, {"x": 0, "y": 0}))
    assert h.clicked, "un fallo de la CORTESÍA se llevaba por delante la acción entera"


def test_y_no_se_propaga_como_fallo_de_la_tarea():
    """This is what the worker interpreted as a dead end: Exit code 1 on a click that was possible."""
    page, h = _Page(), _Handle(scroll=RuntimeError("Timeout 5000ms exceeded"), box={"x": 10, "y": 20,
                                                                                    "width": 40, "height": 10})
    _run(dom._human_click_handle(page, h, {"x": 0, "y": 0}))
    assert page.mouse.clicks, "con caja válida se sigue clicando como una persona, en coordenadas"


def test_un_elemento_DESPEGADO_del_DOM_tampoco_tumba_la_accion():
    """`bounding_box()` on a detached handle blows up. The normal click is the one that knows how to explain why."""
    page, h = _Page(), _Handle(box=RuntimeError("Element is not attached to the DOM"))
    _run(dom._human_click_handle(page, h, {"x": 0, "y": 0}))
    assert h.clicked


# ── the other direction: the good path remains unchanged ──────────────────────────────────────────────────────

def test_con_todo_en_su_sitio_el_clic_sigue_siendo_HUMANO():
    """Sensitivity: if this broke, every click would go through Playwright's `click()` and we would lose the
    disguise —curve, jitter, and pause— that is precisely what keeps us from being treated like a robot."""
    page, h = _Page(), _Handle(box={"x": 100, "y": 200, "width": 50, "height": 20})
    _run(dom._human_click_handle(page, h, {"x": 0, "y": 0}))
    assert page.mouse.clicks and not h.clicked
    x, y = page.mouse.clicks[0]
    assert 100 <= x <= 155 and 200 <= y <= 225, "el clic cae DENTRO de la caja, con su jitter"


def test_sin_caja_se_cae_al_clic_normal_y_no_se_inventa_una_posicion():
    """An element without layout has nowhere to click: inventing coordinates would mean clicking something else."""
    page, h = _Page(), _Handle(box=None)
    _run(dom._human_click_handle(page, h, {"x": 0, "y": 0}))
    assert h.clicked and not page.mouse.clicks


def test_escribir_hereda_la_misma_proteccion():
    """`_human_type_handle` focuses by clicking, so it suffered from the same failure: being unable to bring the
    element into view left a field that could be filled unwritten."""
    page = _Page()
    h = _Handle(scroll=RuntimeError("Timeout 5000ms exceeded"), box=None)

    async def _fill(_):
        pass

    async def _type(text, delay=None):
        page.typed = text

    async def _press(key):
        page.pressed = key

    h.fill = _fill
    page.keyboard = type("K", (), {"type": staticmethod(_type), "press": staticmethod(_press)})()
    _run(dom._human_type_handle(page, h, "monitor 27 pulgadas", True, {"x": 0, "y": 0}))
    assert getattr(page, "typed", "") == "monitor 27 pulgadas"
    assert getattr(page, "pressed", "") == "Enter"
