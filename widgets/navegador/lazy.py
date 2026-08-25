"""widgets/navegador/lazy.py — materializar lo que una página pinta AL ACERCARSE (V2-323).

Un listado VIRTUALIZADO no crea sus fichas hasta que te acercas a ellas, así que «cero filas extraídas» y «la
página no tiene resultados» son dos cosas distintas que se leen igual. Medido el 2026-08-25 contra la URL exacta
que acababa de conducir un worker (`autoscout24.es/lst/cit_madrid/ft_diesel?…`):

    sin desplazarse : 0 anclas de anuncio en el DOM · 1 fila (mobiliario)
    tras desplazarse: 40 anclas                     · 19 filas

HTTP 200, título correcto, y el texto de la propia página decía «16.752 coches de segunda mano diésel». La ronda
(`search-buy-used-car__es`, 19:11) reportó hoja vacía tras cuatro minutos de navegación real.

MÓDULO PROPIO y no un método más de `owner.TaskBrowser` porque el trinquete de arquitectura lo pidió al crecer
ese fichero — y tenía razón por debajo del recuento: esto es mecánica de página, no estado de la pestaña. Recibe
la página y no sabe nada de tareas, hojas ni workers.
"""
from __future__ import annotations

import asyncio
import os

#: Cuánto más alta que la pantalla tiene que ser una página para creer que esconde filas debajo del pliegue.
#: Medido: autoscout24 CON resultados 11,5× · una búsqueda de verdad vacía (wallapop) 0,2×. El 2 está lejos de
#: las dos, y es lo que hace que este mecanismo RESPETE el argumento de coste de V2-294 en vez de pisarlo: una
#: página de resultados sin nada no llega ni a una pantalla, así que nunca paga por esto.
FOLD_RATIO = float(os.environ.get("ZAELAR_NAV_FOLD_RATIO", "2") or 2)
FOLD_STEPS = int(os.environ.get("ZAELAR_NAV_FOLD_STEPS", "4") or 4)
_STEP_WAIT_S = 0.7
_SETTLE_S = 1.2


async def materialise_below_the_fold(page) -> bool:
    """Recorre la página para forzar a que aparezcan las filas perezosas, y DEVUELVE LA VISTA a su sitio.

    `True` = empujó (había contenido debajo del pliegue). `False` = no había nada que materializar, y quien
    llama debe leerlo como «esta página está vacía de verdad», no como un fallo.

    La vuelta de la vista no es limpieza: el `click_at` siguiente del worker lleva coordenadas de una foto
    tomada ANTES de esto, y una herramienta que mueve la página por debajo rompería el clicar para arreglar el
    extraer. Comprobado en vivo: las fichas materializadas SOBREVIVEN a la vuelta arriba.

    Se usa la página directamente y no `agent_act("scroll")` porque ese captura una pantalla por paso: cuatro
    empujones costarían cuatro PNG y cuatro hitos por un movimiento que nadie pidió ver.

    Fail-soft como todo el módulo: si algo se rompe devuelve `False` y la extracción sigue su camino.
    """
    try:
        alto, viewport, y0 = await page.evaluate(
            "() => [document.body.scrollHeight, window.innerHeight, window.scrollY]")
        if not viewport or viewport <= 0 or alto <= viewport * FOLD_RATIO:
            return False
        for _ in range(FOLD_STEPS):
            await page.mouse.wheel(0, viewport)
            await asyncio.sleep(_STEP_WAIT_S)
        await asyncio.sleep(_SETTLE_S)
        await page.evaluate("y => window.scrollTo(0, y)", float(y0 or 0))
        await asyncio.sleep(0.2)
        return True
    except Exception:  # noqa: BLE001
        return False
