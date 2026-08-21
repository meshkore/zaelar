"""Traer el elemento a la vista es una CORTESÍA, no el clic (V2-247).

Medido por el arnés el 2026-08-21, entre las causas que V2-236 dejó abiertas: **tres
`ElementHandle.scroll_into_view_if_needed` con Exit code 1 en un mismo worker**, y ese worker muerto. El
`scroll_into_view_if_needed` estaba SIN proteger al principio de `_human_click_handle`, así que un elemento
tapado, dentro de un acordeón cerrado, sin layout o despegado a mitad se llevaba por delante la acción entera —
aunque el clic siguiera siendo perfectamente posible: `h.click()` de Playwright hace su propio scroll y su propia
espera.

Por qué existe la cortesía: el clic humano se da en COORDENADAS (curva de Bézier + jitter, `_human_move`), así
que el elemento tiene que estar en pantalla para que el ratón caiga donde el usuario lo vería. Cuando eso no se
puede, la respuesta correcta no es rendirse: es clicar por la vía normal y perder el disfraz, no la tarea.
"""
import asyncio

import pytest

from widgets.navegador import dom


class _Handle:
    """Un `ElementHandle` de mentira. `scroll` y `box` deciden qué le pasa a cada llamada."""

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


# ── el caso medido ───────────────────────────────────────────────────────────────────────────────────────────

def test_si_no_se_puede_traer_a_la_vista_SE_CLICA_igual():
    page, h = _Page(), _Handle(scroll=RuntimeError("Timeout 5000ms exceeded"), box=None)
    _run(dom._human_click_handle(page, h, {"x": 0, "y": 0}))
    assert h.clicked, "un fallo de la CORTESÍA se llevaba por delante la acción entera"


def test_y_no_se_propaga_como_fallo_de_la_tarea():
    """Es lo que el worker leía como callejón sin salida: Exit code 1 sobre un clic que era posible."""
    page, h = _Page(), _Handle(scroll=RuntimeError("Timeout 5000ms exceeded"), box={"x": 10, "y": 20,
                                                                                    "width": 40, "height": 10})
    _run(dom._human_click_handle(page, h, {"x": 0, "y": 0}))
    assert page.mouse.clicks, "con caja válida se sigue clicando como una persona, en coordenadas"


def test_un_elemento_DESPEGADO_del_DOM_tampoco_tumba_la_accion():
    """`bounding_box()` sobre un handle despegado revienta. Ahí el clic normal es el que sabe decir por qué."""
    page, h = _Page(), _Handle(box=RuntimeError("Element is not attached to the DOM"))
    _run(dom._human_click_handle(page, h, {"x": 0, "y": 0}))
    assert h.clicked


# ── la otra dirección: el camino bueno no cambia ─────────────────────────────────────────────────────────────

def test_con_todo_en_su_sitio_el_clic_sigue_siendo_HUMANO():
    """Sensibilidad: si esto se rompiera, cada clic pasaría por el `click()` de Playwright y perderíamos el
    disfraz —curva, jitter y pausa— que es justo lo que evita que nos traten como a un robot."""
    page, h = _Page(), _Handle(box={"x": 100, "y": 200, "width": 50, "height": 20})
    _run(dom._human_click_handle(page, h, {"x": 0, "y": 0}))
    assert page.mouse.clicks and not h.clicked
    x, y = page.mouse.clicks[0]
    assert 100 <= x <= 155 and 200 <= y <= 225, "el clic cae DENTRO de la caja, con su jitter"


def test_sin_caja_se_cae_al_clic_normal_y_no_se_inventa_una_posicion():
    """Un elemento sin layout no tiene dónde clicar: inventar coordenadas sería clicar en otra cosa."""
    page, h = _Page(), _Handle(box=None)
    _run(dom._human_click_handle(page, h, {"x": 0, "y": 0}))
    assert h.clicked and not page.mouse.clicks


def test_escribir_hereda_la_misma_proteccion():
    """`_human_type_handle` enfoca clicando, así que arrastraba el mismo fallo: no poder traer a la vista dejaba
    sin escribir un campo que se podía rellenar."""
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
