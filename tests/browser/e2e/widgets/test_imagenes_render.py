"""V2-457 — el visor de imágenes RENDERIZADO, no leído.

Existe por lo que encontró: `flechas: 0`. El manejador de `onerror` —el que dice «esta imagen ya no carga desde
su origen, prueba con la siguiente»— vaciaba el ESCENARIO entero, y con él las flechas ‹ ›. O sea que en el
único caso donde de verdad hacen falta, el aviso te decía que pasaras a la siguiente **y te quitaba la forma de
llegar**. Una foto colgada de un CDN ajeno se cae a menudo, así que no es un borde raro.

Nada de eso da error en consola ni rompe un test que lea el fuente: es la lección del nodo 4.19 (un canvas que
no pinta, sin un solo error) aplicada a otro widget. Se mide con píxeles y con el DOM montado.
"""
from __future__ import annotations

import asyncio
import json
import os

import pytest

ENG = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
_WIDGET = os.path.join(ENG, "widgets", "imagenes", "widget.js")

_DATOS = {
    "title": "Ferrari Amalfi", "query": "Ferrari Amalfi", "source": "google", "n": 3, "i": 0,
    "items": [
        {"url": "https://no.resuelve.invalid/a.jpg", "thumb": "https://no.resuelve.invalid/t1.jpg",
         "title": "Ferrari Amalfi - Ferrari.com", "site": "www.ferrari.com",
         "page": "https://www.ferrari.com/x", "w": 1080, "h": 565, "weight": "68KB"},
        {"url": "https://no.resuelve.invalid/b.jpg", "title": "Wikipedia", "site": "es.wikipedia.org",
         "page": "https://es.wikipedia.org/y", "w": 3128, "h": 2333},
        {"url": "https://no.resuelve.invalid/c.jpg", "title": "Press", "site": "www.netcarshow.com",
         "page": "https://z", "w": 3748, "h": 2811},
    ],
}
_DATOS["current"] = _DATOS["items"][0]

_HTML = """<!doctype html><html data-theme="dark"><head><meta charset="utf-8"><style>
:root{--hb-bg:#0f1720;--hb-bg-soft:#16202b;--hb-ink:#e8eef6;--hb-muted:#9fb0c4;--hb-muted-2:#6f8299;
      --hb-line:#243244;--hb-accent:#2F6FEB;--hb-accent2:#16B8A6}
body{margin:0;background:#0a1017;display:flex;justify-content:center;padding:20px}
</style></head><body><div id="host"></div></body></html>"""

_MEDIR = """() => {
  const el = document.querySelector('.hb-imgv');
  if (!el) return {montado: false};
  const st = el.querySelector('.imgstage');
  const src = el.querySelector('.imgsrc');
  return {
    montado: true,
    titulo: (el.querySelector('.imghd b') || {}).textContent || '',
    contador: (el.querySelector('.imgcount') || {}).textContent || '',
    sitio: (src && src.textContent || '').trim(),
    enlace_a_la_pagina: !!(src && src.querySelector('a[href^="http"]')),
    alto_escenario: Math.round(st.getBoundingClientRect().height),
    miniaturas: el.querySelectorAll('.imgthumb').length,
    marcadas: el.querySelectorAll('.imgthumb.on').length,
    flechas: el.querySelectorAll('.imgnav').length,
    aviso: (el.querySelector('.imgstage .imgempty') || {}).textContent || '',
  };
}"""


def _pintar(datos):
    async def run():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            b = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
            pg = await b.new_page(viewport={"width": 820, "height": 640})
            errores = []
            pg.on("pageerror", lambda e: errores.append(str(e)))
            await pg.set_content(_HTML)
            src = open(_WIDGET, encoding="utf-8").read()
            await pg.add_script_tag(
                content=src.replace("export function render", "window.render = function render"))
            await pg.evaluate("d => window.render(document.getElementById('host'), d, {action: () => {}})", datos)
            await pg.wait_for_timeout(500)          # deja que fallen las imágenes y corra `onerror`
            m = await pg.evaluate(_MEDIR)
            m["errores"] = errores
            await b.close()
            return m
    return asyncio.run(run())


@pytest.fixture(scope="module")
def visto():
    try:
        import playwright  # noqa: F401
    except Exception:  # pragma: no cover
        pytest.skip("playwright no instalado")
    return _pintar(_DATOS)


def test_se_monta_y_sin_un_solo_error(visto):
    assert visto["montado"], "el visor no llegó a pintarse"
    assert visto["errores"] == [], visto["errores"]


def test_las_flechas_SOBREVIVEN_a_una_imagen_que_no_carga(visto):
    """EL defecto que este fichero existe para cazar. Con las tres fotos caídas (dominio inexistente), el aviso
    tiene que estar Y las flechas también: decirle al operador «prueba con la siguiente» quitándole el botón de
    pasar a la siguiente es peor que no decir nada."""
    assert visto["aviso"], "una imagen caída tiene que DECIRSE, no dejar el hueco roto del navegador"
    assert visto["flechas"] == 2, (
        f"flechas={visto['flechas']} — el manejador de error se llevó por delante la navegación")


def test_la_fuente_se_ve_y_lleva_a_su_pagina(visto):
    """Lo que el operador pidió explícitamente: «incluso con la fuente de la misma». El SITIO se nombra y la
    PÁGINA se enlaza — una URL de CDN dice `cdn.ferrari.com` y no quién lo publicó."""
    assert "ferrari.com" in visto["sitio"]
    assert "1080×565" in visto["sitio"], "las dimensiones ayudan a elegir y son gratis"
    assert visto["enlace_a_la_pagina"]


def test_la_foto_manda_en_la_pantalla(visto):
    """Un visor cuya imagen grande es una franja no es un visor. El escenario se lleva la mayor parte del alto."""
    assert visto["alto_escenario"] >= 260, visto["alto_escenario"]


def test_la_tira_esta_entera_y_marca_la_que_se_esta_viendo(visto):
    assert visto["miniaturas"] == 3
    assert visto["marcadas"] == 1, "sin marca, la tira no dice dónde estás"
    assert visto["contador"] == "1 / 3"


def test_con_UNA_sola_foto_no_hay_ni_flechas_ni_tira():
    """La mitad simétrica: unas flechas que no llevan a ninguna parte y una tira de un elemento son ruido."""
    uno = {**_DATOS, "n": 1, "items": _DATOS["items"][:1]}
    uno["current"] = uno["items"][0]
    m = _pintar(uno)
    assert m["montado"] and m["flechas"] == 0 and m["miniaturas"] == 0


def test_sin_fotos_lo_dice_en_vez_de_dejar_una_caja_vacia():
    m = _pintar({"title": "", "query": "", "source": "", "n": 0, "i": 0, "items": [], "current": {}})
    assert m["montado"] and m["aviso"] and m["flechas"] == 0
