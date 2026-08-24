"""Leer una ficha sin perder el listado (2026-08-24).

Petición del operador: *«el propio brain worker tiene que encargarse de extraer datos, modelar las
diferentes fichas, abrir bastantes pestañas para investigar y valorar cada una de las fichas de
resultados»*. No podía: el puente solo sabía `navigate`, que se lleva la ÚNICA pestaña — así que mirar un
anuncio costaba perder el listado y volver a buscarlo, **dos navegaciones por ficha**, con el buscador y los
filtros de por medio. A 7-11 s cada una, valorar tres fichas se comía la conversación entera.

Medido con el verbo nuevo contra el plató vivo (es.wallapop.com):

    navigate al listado   8,24 s
    extract               0,02 s → 6 fichas
    visit ficha #1        0,85 s   ← y el listado sigue donde estaba
    visit (repetido)      0,59 s
    extract               0,01 s → las MISMAS 6

Lo que devuelve es lo que hace falta para VALORAR —título, texto de la ficha, listados declarados— y no una
captura: valorar diez fichas por visión son diez lecturas de PNG, y esto tiene que poder hacerse muchas
veces.
"""
import inspect

from nucleo import nav_cli
from widgets.navegador import act_api, owner


def _code(fn):
    return "\n".join(l for l in inspect.getsource(fn).splitlines() if not l.strip().startswith("#"))


def test_la_ficha_se_lee_en_OTRA_pestana():
    src = _code(owner.TaskBrowser.visit)
    assert "ctx.new_page()" in src, "sin pestaña propia esto es un `navigate` con otro nombre"


def test_NUNCA_se_toca_la_pestana_del_listado():
    """Es la razón de existir del verbo: si tocara `self.page`, el listado se perdería igual."""
    src = _code(owner.TaskBrowser.visit)
    assert "self.page =" not in src and "self._goto" not in src


def test_la_pestana_se_cierra_SIEMPRE():
    """Una pestaña huérfana por ficha es cómo se llega a las treinta que ya midió `_reap_popups`. El cierre
    va en `finally`, así que también ocurre cuando la lectura revienta."""
    src = _code(owner.TaskBrowser.visit)
    i = src.find("finally:")
    assert i > 0, "sin `finally` una ficha que falla deja su pestaña abierta"
    assert "tab.close()" in src[i:]


def test_prefiere_el_CONTENIDO_al_MENU():
    """Medido en la primera prueba: `body.innerText` empezaba por «Todas las categorías Coches Motos Motor y
    accesorios…». Con el texto recortado, eso deja al worker valorando una ficha por el menú del sitio —
    la misma forma que V2-234 midió en la extracción, por la otra puerta.

    La regla es ESTRUCTURAL, no una lista de sitios: si la página declara su contenido principal se lee eso;
    si no, el cuerpo entero, que es lo que había."""
    src = _code(owner.TaskBrowser.visit)
    assert "main, article, [role=main]" in src
    assert "document.body" in src, "sin contenido declarado hay que caer al cuerpo, no devolver vacío"


def test_las_lecturas_estan_ACOTADAS():
    """Mismo motivo que la mirada: `evaluate` no tiene timeout en Playwright, y una ficha lenta no puede
    llevarse la ronda."""
    src = _code(owner.TaskBrowser.visit)
    assert src.count("asyncio.wait_for") >= 3
    assert "_DOM_TIMEOUT_S" in src


def test_un_fallo_de_la_ficha_NO_lanza():
    """El worker va a visitar muchas: una ficha caída tiene que devolver un `ok:false` legible y seguir, no
    tumbar la acción."""
    src = _code(owner.TaskBrowser.visit)
    assert '"ok": False' in src and "error" in src


def test_el_WORKER_puede_llamarlo():
    """Una capacidad que el puente no expone no existe para el worker (misma lección que el nodo 4.20)."""
    src = inspect.getsource(nav_cli.main)
    assert 'sub.add_parser("visit"' in src
    assert '_act("visit"' in src
    assert "NO pierdes el listado" in src, "el worker tiene que saber PARA QUÉ sirve, o seguirá usando navigate"


def test_el_puente_HTTP_lo_enruta():
    src = inspect.getsource(act_api)
    assert 'if action == "visit":' in src


def test_el_PROMPT_del_worker_lo_nombra_y_dice_para_que_sirve():
    """Un verbo que el prompt no explica se queda sin usar — la lección de V2-219, donde el worker se moría
    aprendiendo su propio CLI a tientas. Y el inventario cerrado de subcomandos tiene que incluirlo, o el
    propio prompt le dice que no existe."""
    import inspect
    from nucleo import dispatch_prompts as dp
    src = inspect.getsource(dp)
    assert "nav_cli visit" in src
    assert "sin perder el listado" in src, "hay que decirle PARA QUÉ, no solo que existe"
    i = src.find("ESOS son TODOS los subcomandos")
    assert i > 0 and "visit" in src[i:i + 400], (
        "el inventario cerrado le diría que `visit` no existe y no lo usaría nunca")
